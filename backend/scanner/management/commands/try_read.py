"""Run the paid half of the pipeline over a handful of spines.

A full shelf photo is ~100 crops, which is ~17 API calls. This command proves
the whole path — detect, crop, read, match — for a fraction of that, so a
broken prompt or a wrong model id costs one call to find rather than
seventeen. Nothing is written to the database.
"""

import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from scanner import detection, vlm
from scanner.matching import Matcher, load_catalog


class Command(BaseCommand):
    help = "Read the first N detected spines from a photo and match them."

    def add_arguments(self, parser):
        parser.add_argument("image", help="Path to a shelf photo.")
        parser.add_argument(
            "-n", "--limit", type=int, default=6,
            help="How many spines to read (default 6, which is one batch).",
        )
        parser.add_argument(
            "--start", type=int, default=0,
            help="Skip this many spines first, to sample a different part of the shelf.",
        )

    def handle(self, *args, **options):
        source = Path(options["image"])
        if not source.exists():
            raise SystemExit(f"No such file: {source}")

        t0 = time.perf_counter()
        detections = detection.detect_spines(source)
        detect_ms = (time.perf_counter() - t0) * 1000
        self.stdout.write(
            f"{len(detections)} spines detected in {detect_ms:.0f} ms"
        )
        if not detections:
            self.stdout.write(self.style.WARNING("Nothing to read."))
            return

        start = max(0, options["start"])
        chosen = detections[start : start + options["limit"]]
        if not chosen:
            raise SystemExit("--start is past the last detection.")

        out_dir = Path(settings.MEDIA_ROOT) / "try_read"
        crops = []
        for det in chosen:
            path = out_dir / f"{source.stem}-{det.index:03d}.jpg"
            detection.crop_spine(source, det.box, path)
            crops.append(path)
        self.stdout.write(f"Cropped {len(crops)} spines to {out_dir}")

        t0 = time.perf_counter()
        reads, usage = vlm.read_spines(crops)
        vlm_ms = (time.perf_counter() - t0) * 1000

        matcher = Matcher(
            load_catalog(settings.CATALOG_PATH),
            match_threshold=settings.SHELFIE["MATCH_THRESHOLD"],
            review_threshold=settings.SHELFIE["REVIEW_THRESHOLD"],
        )

        self.stdout.write("")
        for det, read in zip(chosen, reads):
            if read.error:
                self.stdout.write(
                    self.style.WARNING(f"  [{det.index:3d}] unreadable: {read.error}")
                )
                continue
            result = matcher.match(read.title, read.author)
            style = {
                "matched": self.style.SUCCESS,
                "review": self.style.WARNING,
                "unmatched": self.style.NOTICE,
            }.get(result.status, self.style.NOTICE)
            self.stdout.write(
                f"  [{det.index:3d}] read: {read.title!r} / {read.author!r}"
            )
            self.stdout.write(
                style(
                    f"        -> {result.status} ({result.confidence:.2f}) "
                    f"{result.match_id or ''}"
                )
            )
            if result.reason:
                self.stdout.write(f"        {result.reason}")

        readable = sum(1 for r in reads if r.is_readable)
        self.stdout.write("")
        self.stdout.write(
            f"read {readable}/{len(reads)} spines in {vlm_ms:.0f} ms  |  "
            f"tokens in {usage['input_tokens']} out {usage['output_tokens']}"
        )
        if usage["input_tokens"]:
            per_spine = usage["input_tokens"] / len(reads)
            self.stdout.write(
                f"per spine: {per_spine:.0f} input tokens  |  "
                f"a {len(detections)}-spine photo would cost about "
                f"{per_spine * len(detections):,.0f} input tokens"
            )
