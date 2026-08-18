"""Match a spine read against the catalog.

Deliberately free of Django imports so it can be tested on its own, without a
database, a photo, or an API key.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

# Articles are dropped from the front of titles so "The Road" and "Road" are
# the same key. They are not dropped mid-title.
ARTICLES = ("the ", "a ", "an ")

# Apostrophes are deleted rather than replaced with a space, so "hitchhiker's"
# normalizes to "hitchhikers" and not "hitchhiker s".
# Words that carry no identity. Two titles sharing only these are not similar,
# however well a character-level ratio scores them.
STOPWORDS = frozenset(
    "the a an of and or in on to for with at by from de la le el il"
    .split()
)

_APOSTROPHE = re.compile(r"['\u2018\u2019\u02bc]")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize(text: str) -> str:
    """Lowercase, de-accent, drop punctuation, collapse whitespace."""
    if not text:
        return ""
    text = strip_accents(text.lower())
    text = text.replace("&", " and ")
    text = _APOSTROPHE.sub("", text)
    text = _PUNCT.sub(" ", text)
    return _WS.sub(" ", text).strip()


def normalize_title(title: str) -> str:
    norm = normalize(title)
    for article in ARTICLES:
        if norm.startswith(article):
            return norm[len(article):]
    return norm


def normalize_author(author: str) -> str:
    """Normalize, and flip 'Last, First' into 'First Last'.

    The comma is the only reliable signal for the flipped form, so it is
    checked before punctuation is stripped.
    """
    if not author:
        return ""
    raw = author.strip()
    if raw.count(",") == 1:
        last, first = (part.strip() for part in raw.split(","))
        if last and first:
            raw = f"{first} {last}"
    return normalize(raw)


def split_multi(value: str) -> list[str]:
    """Catalog columns hold pipe-separated alternates."""
    if not value:
        return []
    return [part.strip() for part in value.split("|") if part.strip()]


@dataclass
class CatalogEntry:
    id: str
    title: str
    author: str
    alt_titles: list[str] = field(default_factory=list)
    alt_authors: list[str] = field(default_factory=list)
    year: str = ""
    publisher: str = ""
    contains_ids: list[str] = field(default_factory=list)

    norm_titles: list[str] = field(default_factory=list, repr=False)
    norm_authors: list[str] = field(default_factory=list, repr=False)
    author_surnames: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self):
        self.norm_titles = _dedupe(
            [normalize_title(t) for t in [self.title, *self.alt_titles] if t]
        )
        self.norm_authors = _dedupe(
            [normalize_author(a) for a in [self.author, *self.alt_authors] if a]
        )
        self.author_surnames = {
            n.split()[-1] for n in self.norm_authors if n.split()
        }

    @property
    def is_omnibus(self) -> bool:
        return bool(self.contains_ids)


def _dedupe(values: list[str]) -> list[str]:
    seen, out = set(), []
    for v in values:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def load_catalog(path: str | Path) -> list[CatalogEntry]:
    entries = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not row.get("title") or not row.get("author"):
                continue
            entries.append(
                CatalogEntry(
                    id=row.get("id") or row["title"],
                    title=row["title"].strip(),
                    author=row["author"].strip(),
                    alt_titles=split_multi(row.get("alt_titles", "")),
                    alt_authors=split_multi(row.get("alt_authors", "")),
                    year=(row.get("year") or "").strip(),
                    publisher=(row.get("publisher") or "").strip(),
                    contains_ids=split_multi(row.get("contains_ids", "")),
                )
            )
    return entries


def content_tokens(norm: str) -> list[str]:
    return [t for t in norm.split() if t not in STOPWORDS]


def shares_content(left: list[str], right: list[str]) -> bool:
    """True if any meaningful word matches, allowing for OCR noise.

    Fuzzy rather than exact so a misread short title ("Emmma" for "Emma")
    is not treated as having nothing in common.
    """
    if not left or not right:
        # One side is entirely stopwords; the gate cannot say anything useful.
        return True
    for a in left:
        for b in right:
            if a == b or fuzz.ratio(a, b) >= 80:
                return True
    return False


@dataclass
class Candidate:
    entry: CatalogEntry
    score: float
    title_score: float
    author_score: float | None

    def as_dict(self) -> dict:
        return {
            "id": self.entry.id,
            "title": self.entry.title,
            "author": self.entry.author,
            "year": self.entry.year,
            "publisher": self.entry.publisher,
            "score": round(self.score, 4),
            "title_score": round(self.title_score, 4),
            "author_score": (
                None if self.author_score is None else round(self.author_score, 4)
            ),
        }


@dataclass
class MatchResult:
    status: str          # matched | review | unmatched
    confidence: float
    match_id: str | None
    candidates: list[Candidate]
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "confidence": round(self.confidence, 4),
            "match_id": self.match_id,
            "reason": self.reason,
            "candidates": [c.as_dict() for c in self.candidates],
        }


# Weights. Title carries more than author because spines show the title larger
# and the VLM reads it more reliably; author is the tiebreaker that separates
# two different books sharing a title.
# A title whose meaningful words have nothing in common with a candidate is
# capped here, no matter what the fuzzy ratio says. Without this, "Song of the
# Sun God" scores 0.72 against "The Lord of the Rings" on the strength of "of
# the", and books that are simply not in the catalog surface as review
# candidates instead of being reported as unmatched.
NO_CONTENT_OVERLAP_CAP = 0.45

TITLE_WEIGHT = 0.65
AUTHOR_WEIGHT = 0.35
# Applied when the spine gave a title but no author: the match cannot be
# corroborated, so it should not reach full confidence on its own.
NO_AUTHOR_DISCOUNT = 0.90

MATCH_THRESHOLD = 0.85
REVIEW_THRESHOLD = 0.55
# Below this gap between first and second place, the top candidate is not
# meaningfully better than the runner-up and the result belongs to a human.
MARGIN_FLOOR = 0.10


class Matcher:
    def __init__(
        self,
        entries: list[CatalogEntry],
        match_threshold: float = MATCH_THRESHOLD,
        review_threshold: float = REVIEW_THRESHOLD,
    ):
        self.entries = entries
        self.by_id = {e.id: e for e in entries}
        self.match_threshold = match_threshold
        self.review_threshold = review_threshold
        self._index = self._build_index(entries)

    @staticmethod
    def _build_index(entries: list[CatalogEntry]) -> dict[str, set[int]]:
        """Token -> entry positions, so scoring runs on a shortlist."""
        index: dict[str, set[int]] = {}
        for pos, entry in enumerate(entries):
            for norm in entry.norm_titles:
                for token in norm.split():
                    index.setdefault(token, set()).add(pos)
            for surname in entry.author_surnames:
                index.setdefault(surname, set()).add(pos)
        return index

    def _shortlist(self, norm_title: str, norm_author: str) -> list[CatalogEntry]:
        tokens = set(norm_title.split()) | set(norm_author.split())
        positions: set[int] = set()
        for token in tokens:
            positions |= self._index.get(token, set())
        if not positions:
            # Nothing shares a token — the read is likely garbled. Fall back to
            # the whole catalog rather than returning nothing, and let the
            # scores decide.
            return self.entries
        return [self.entries[p] for p in positions]

    @staticmethod
    def _title_score(norm_title: str, entry: CatalogEntry) -> float:
        best = 0.0
        read_content = content_tokens(norm_title)
        for cand in entry.norm_titles:
            score = max(
                fuzz.ratio(norm_title, cand),
                fuzz.token_sort_ratio(norm_title, cand),
            ) / 100
            # A title that is contained in a longer title ("Road" inside "Road
            # Less Traveled", "Dune" inside "Dune Messiah") must not score as a
            # near-match. Cap it by how much of the longer title it covers.
            if score < 1.0 and (norm_title in cand or cand in norm_title):
                shorter, longer = sorted([norm_title, cand], key=len)
                coverage = len(shorter) / max(len(longer), 1)
                # Above this coverage the difference is a typo or a dropped
                # word, not a genuinely shorter title, so no penalty applies.
                if coverage < 0.85:
                    score = min(score, 0.50 + 0.35 * coverage)
            if not shares_content(read_content, content_tokens(cand)):
                score = min(score, NO_CONTENT_OVERLAP_CAP)
            best = max(best, score)
        return best

    @staticmethod
    def _author_score(norm_author: str, entry: CatalogEntry) -> float:
        if not norm_author:
            return 0.0
        best = 0.0
        for cand in entry.norm_authors:
            best = max(best, fuzz.token_sort_ratio(norm_author, cand) / 100)
        # Spines very often show a surname only. Treat an exact surname hit as
        # strong evidence rather than a poor full-string match.
        tokens = norm_author.split()
        if tokens and tokens[-1] in entry.author_surnames:
            best = max(best, 0.90)
        return best

    def _score(self, norm_title: str, norm_author: str, entry: CatalogEntry) -> Candidate:
        title_score = self._title_score(norm_title, entry)
        if norm_author:
            author_score = self._author_score(norm_author, entry)
            score = TITLE_WEIGHT * title_score + AUTHOR_WEIGHT * author_score
        else:
            author_score = None
            score = title_score * NO_AUTHOR_DISCOUNT
        return Candidate(entry, score, title_score, author_score)

    def _confidence(self, ranked: list[Candidate]) -> tuple[float, str]:
        top = ranked[0].score
        if len(ranked) < 2:
            return top, ""
        margin = top - ranked[1].score
        if margin >= MARGIN_FLOOR:
            return top, ""
        # Scale confidence down toward the review band as the gap closes. A
        # 0.98 match with a 0.98 runner-up is ambiguous, not confident.
        scaled = min(top, self.review_threshold + margin * 3.0)
        reason = (
            f"ambiguous: '{ranked[1].entry.title}' scored within "
            f"{margin:.2f} of '{ranked[0].entry.title}'"
        )
        if self._related(ranked[0].entry, ranked[1].entry):
            reason = (
                f"ambiguous: '{ranked[0].entry.title}' and "
                f"'{ranked[1].entry.title}' are the same work in different "
                f"forms (omnibus/volume or edition)"
            )
        return scaled, reason

    def _related(self, a: CatalogEntry, b: CatalogEntry) -> bool:
        """Omnibus vs contained volume, or two editions of one book."""
        if b.id in a.contains_ids or a.id in b.contains_ids:
            return True
        return bool(set(a.norm_titles) & set(b.norm_titles)) and bool(
            set(a.norm_authors) & set(b.norm_authors)
        )

    def match(self, title: str, author: str = "", top_n: int = 5) -> MatchResult:
        norm_title = normalize_title(title or "")
        norm_author = normalize_author(author or "")

        if not norm_title and not norm_author:
            return MatchResult("unmatched", 0.0, None, [], "nothing readable")

        shortlist = self._shortlist(norm_title, norm_author)
        ranked = sorted(
            (self._score(norm_title, norm_author, e) for e in shortlist),
            key=lambda c: c.score,
            reverse=True,
        )[:top_n]

        if not ranked or ranked[0].score < self.review_threshold:
            return MatchResult(
                "unmatched", ranked[0].score if ranked else 0.0, None, ranked,
                "no catalog entry scored above the review threshold",
            )

        confidence, reason = self._confidence(ranked)
        if confidence >= self.match_threshold:
            return MatchResult("matched", confidence, ranked[0].entry.id, ranked, reason)
        if confidence >= self.review_threshold:
            return MatchResult("review", confidence, ranked[0].entry.id, ranked, reason)
        return MatchResult("unmatched", confidence, None, ranked, reason)

    def search(self, query: str, limit: int = 10) -> list[Candidate]:
        """Backs manual correction in the review step."""
        norm = normalize_title(query or "")
        if not norm:
            return []
        shortlist = self._shortlist(norm, "")
        ranked = sorted(
            (self._score(norm, "", e) for e in shortlist),
            key=lambda c: c.score,
            reverse=True,
        )
        return ranked[:limit]
