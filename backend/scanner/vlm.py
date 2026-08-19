"""Hosted vision-language reads.

The only paid step in the pipeline. Crops are batched so one request covers
several spines, and the response is parsed per item so a single malformed
entry costs one book rather than the whole batch.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

PROMPT = """You are reading the spines of books photographed on a shelf.

You will be given {n} cropped images, numbered 0 to {last}. Each crop should
contain exactly one book spine, rotated so the text reads left to right. Some
spines are printed the other way up and will appear upside down; read those
too. Neighbouring books are often visible at the edges of a crop — read only
the book in the middle.

For each crop, return the title and author exactly as printed. Do not guess,
correct, complete, or translate them. If a crop is blurred, cropped badly,
contains no book, or you cannot read it, return null for the fields you
cannot read.

Respond with JSON only, no prose, in exactly this shape:

{{"reads": [{{"index": 0, "title": "...", "author": "..."}}]}}

Use null rather than an empty string or a guess for anything unreadable."""


@dataclass
class SpineRead:
    index: int
    title: str = ""
    author: str = ""
    error: str = ""

    @property
    def is_readable(self) -> bool:
        return bool(self.title or self.author)


class VLMUnavailable(RuntimeError):
    pass


def _client():
    import os

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise VLMUnavailable("ANTHROPIC_API_KEY is not set")
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover
        raise VLMUnavailable("the anthropic package is not installed") from exc
    return Anthropic(api_key=api_key, timeout=settings.SHELFIE["VLM_TIMEOUT_SECONDS"])


def _encode(path: Path) -> dict:
    data = base64.standard_b64encode(Path(path).read_bytes()).decode()
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
    }


def _extract_json(text: str) -> dict:
    """Parse the model's reply, tolerating fences and leading prose."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Last resort: the outermost object in the reply.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : start + (end - start + 1)])
    raise json.JSONDecodeError("no JSON object in reply", text, 0)


def _clean(value) -> str:
    if value is None:
        return ""
    value = str(value).strip()
    return "" if value.lower() in {"null", "none", "unknown", "n/a", ""} else value


def read_batch(crop_paths: list[Path], offset: int = 0) -> tuple[list[SpineRead], dict]:
    """Read one batch. Never raises: failures come back as SpineRead.error."""
    usage = {"input_tokens": 0, "output_tokens": 0}
    if not crop_paths:
        return [], usage

    try:
        client = _client()
    except VLMUnavailable as exc:
        return [
            SpineRead(index=offset + i, error=str(exc))
            for i in range(len(crop_paths))
        ], usage

    content: list[dict] = [
        {"type": "text", "text": PROMPT.format(n=len(crop_paths), last=len(crop_paths) - 1)}
    ]
    for i, path in enumerate(crop_paths):
        content.append({"type": "text", "text": f"Crop {i}:"})
        content.append(_encode(path))

    last_error = ""
    for attempt in range(settings.SHELFIE["VLM_MAX_RETRIES"] + 1):
        try:
            response = client.messages.create(
                model=settings.SHELFIE["VLM_MODEL"],
                max_tokens=1024,
                messages=[{"role": "user", "content": content}],
            )
            usage["input_tokens"] = getattr(response.usage, "input_tokens", 0)
            usage["output_tokens"] = getattr(response.usage, "output_tokens", 0)
            payload = _extract_json(response.content[0].text)
            return _to_reads(payload, len(crop_paths), offset), usage
        except json.JSONDecodeError as exc:
            # Retrying a malformed reply is worth one attempt; it is usually
            # non-deterministic.
            last_error = f"malformed JSON from the model: {exc}"
            logger.warning("%s (attempt %s)", last_error, attempt + 1)
        except Exception as exc:  # network, timeout, rate limit, API error
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("VLM call failed: %s (attempt %s)", last_error, attempt + 1)
        if attempt < settings.SHELFIE["VLM_MAX_RETRIES"]:
            time.sleep(2 ** attempt)

    return [
        SpineRead(index=offset + i, error=last_error) for i in range(len(crop_paths))
    ], usage


def _to_reads(payload: dict, count: int, offset: int) -> list[SpineRead]:
    """Map the reply onto one SpineRead per crop, salvaging per item.

    Any crop the model omitted, or returned unusable data for, becomes an
    unreadable spine rather than silently disappearing from the scan.
    """
    reads = {i: SpineRead(index=offset + i, error="not returned by the model")
             for i in range(count)}
    entries = payload.get("reads") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        entries = []

    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        try:
            index = int(entry.get("index", position))
        except (TypeError, ValueError):
            index = position
        if index not in reads:
            continue
        title, author = _clean(entry.get("title")), _clean(entry.get("author"))
        if title or author:
            reads[index] = SpineRead(offset + index, title=title, author=author)
        else:
            reads[index] = SpineRead(offset + index, error="spine was not readable")

    return [reads[i] for i in range(count)]


def read_spines(crop_paths: list[Path]) -> tuple[list[SpineRead], dict]:
    """Read every crop. Returns reads in spine order plus total token usage.

    Batches run concurrently. Reads were 82% of end-to-end latency when they
    ran one after another, and since each batch is an independent request the
    only thing serialising them was the loop. Concurrency changes no token
    counts, so the cost is identical; it is latency that drops.

    Failures are already contained inside read_batch, which never raises, so a
    slow or failing batch cannot take the others down with it.
    """
    size = max(1, settings.SHELFIE["VLM_BATCH_SIZE"])
    batches = [
        (start, crop_paths[start : start + size])
        for start in range(0, len(crop_paths), size)
    ]
    totals = {"input_tokens": 0, "output_tokens": 0}
    if not batches:
        return [], totals

    workers = max(1, min(settings.SHELFIE["VLM_CONCURRENCY"], len(batches)))
    results: dict[int, list[SpineRead]] = {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(read_batch, chunk, start): start for start, chunk in batches
        }
        for future in as_completed(futures):
            start = futures[future]
            try:
                reads, usage = future.result()
            except Exception as exc:  # pragma: no cover - read_batch swallows its own
                logger.exception("batch at %s failed outright", start)
                size_of = len(dict(batches)[start])
                reads = [
                    SpineRead(index=start + i, error=f"{type(exc).__name__}: {exc}")
                    for i in range(size_of)
                ]
                usage = {"input_tokens": 0, "output_tokens": 0}
            results[start] = reads
            totals["input_tokens"] += usage["input_tokens"]
            totals["output_tokens"] += usage["output_tokens"]

    # Reassemble in spine order; completion order is not request order.
    all_reads: list[SpineRead] = []
    for start, _ in batches:
        all_reads.extend(results[start])
    return all_reads, totals
