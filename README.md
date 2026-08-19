# Shelfie — Bookshelf → Library Inventory

Photo of a bookshelf → structured personal library.

Expo app → Django REST API → local model detects spines → hosted VLM reads
title/author → matched against `catalog.csv` with a confidence score → low
confidence goes to a review step → confirmed books persist to SQLite.

## Setup

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add ANTHROPIC_API_KEY
python manage.py migrate
python manage.py warmup       # downloads the detector weights (~6 MB)
python manage.py runserver 0.0.0.0:8000
```

`warmup` is not optional on a clean clone. The first prediction after a fresh
weight download returns zero detections instead of raising, so without it the
first scan reports "no books found" on a good photo.

### Frontend

```bash
cd frontend
npm install
npx expo start --web      # or: npx expo start, and scan the QR with Expo Go
```

```
# frontend/.env
EXPO_PUBLIC_API_BASE_URL=http://localhost:8000     # LAN IP for a real device
```

### Tests

```bash
cd backend && pytest
```

24 tests, all on the matching logic. No database, no photo, no API key needed.

### Useful commands

```bash
python manage.py preview_detections test-photos/shelf2.png   # draws the boxes
python manage.py try_read test-photos/shelf2.png -n 6        # one API call
```

## Architecture

```
Expo app                    Django + DRF                     External
camera / picker
     │  POST /api/scans/  (multipart image)
     ▼
                            ScanView
                              ├─ 1. detect spines      ── YOLOv8n, CPU
                              ├─ 2. crop, rotate, upscale
                              ├─ 3. read each spine    ──▶ Claude vision
                              ├─ 4. match vs catalog   ── local, in memory
                              ▼
     ◀──── ScanResult { items[]: status, confidence, candidates[] }
     ├─ matched     → added directly
     ├─ review      → user confirms or corrects
     ├─ unmatched   → user searches or discards
     └─ unreadable  → crop shown, user can type it in
```

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/scans/` | Upload a photo, get per-spine results |
| `GET` | `/api/scans/{id}/` | Re-fetch a scan |
| `POST` | `/api/items/{id}/resolve/` | Confirm, correct, or discard one spine |
| `GET`/`POST` | `/api/library/` | The user's library |
| `GET` | `/api/catalog/search/?q=` | Backs manual correction |

Scans persist before the review step rather than living in app state, so a
review queue survives an app restart.

## Local vs hosted

| | Where |
| --- | --- |
| Spine detection, cropping, rotation, upscaling | Local, CPU |
| Reading title/author off a spine | Hosted (Claude vision) |
| Catalog matching and confidence | Local |

Localization is cheap and off-the-shelf weights handle it. Sending a whole
shelf photo to a VLM and asking for every book at once returns an unstructured
list with no way to tie a title back to a region of the image, which makes the
review step much worse — the user cannot see which book a bad read came from.
Reading rotated, stylized, low-resolution spine text is where a VLM earns its
cost, so that is the only step that is paid for.

Crops are sent 6 per request. The response is parsed per item, so one
malformed entry costs one book rather than the batch.

### Measured latency

One full scan of `test-photos/shelf2.png` (1110x1516, 88 detected spines)
through the app. macOS, Apple Silicon, CPU inference.

| Stage | Measured | Share |
| --- | --- | --- |
| Spine detection, local | 3,562 ms | 20% |
| VLM reads, hosted | 9,391 ms | 52% |
| Matching, local | 188 ms | 1% |
| Upload, decode, crop, save | ~4,900 ms | 27% |
| **End to end** | **18,028 ms** | |

The reads still dominate, and they scale with the number of books while
detection stays flat at about 3.6 s regardless.

Batches originally ran one after another, which put reads at 39,798 ms and the
whole scan at 48,655 ms. Since each batch is an independent request, the only
thing serialising them was the loop. Running five concurrently cut reads by
4.2x and the full scan by 2.7x, for identical token counts: 28,485 input tokens
before and after. Concurrency was pure latency, bought at no cost.

### Measured cost

Same scan as above.

| | Value |
| --- | --- |
| Model | `claude-haiku-4-5` |
| Input tokens, whole photo | 28,485 |
| Output tokens, whole photo | 3,526 |
| Per spine | 324 in / 40 out |
| API calls | 15 |
| All development and testing combined | $0.03 |

Cost is not the constraint here, which is what justified upscaling crops
(below) at roughly 7× the tokens per spine.

### Measured accuracy

Scored by hand against `test-photos/shelf2.png`, a shelf holding 85 books.

**Detection.** The detector returned 88 boxes. All 85 books were found, and the
3 extra boxes were pieces of the shelf itself rather than books. That is full
recall at 97% precision. The false positives cost three wasted API calls and
arrive in the review queue as unreadable, where they are discarded in one tap.

**Reading.** 60 of the 85 book titles were read correctly. The other 25 were too
blurred in the photo to identify by eye either, so they are a limit of the photo
rather than of the model. No book was returned as a different book, and every
unread spine reached the review queue rather than being dropped or guessed at.

Accuracy is therefore bounded by photo quality more than by the model. A sharper
photo of the same shelf would move most of those 25 into the readable group.

## Catalog

`catalog.csv` — 1,000 entries. Title, author, and pipe-separated alternate
titles and author forms; year and publisher on the rows where editions need
separating.

Built in two passes. The first ~160 rows were written to carry specific
ambiguities:

| Ambiguity | Rows |
| --- | --- |
| Two editions of one book | `dune-1965` / `dune-2005`, `1984-signet` / `1984-penguin`, two Bibles |
| One book, two titles | `sorcerers-stone` (Philosopher's Stone), `northern-lights` (The Golden Compass), `and-then-none` (Ten Little Indians) |
| Two books, same title | `idiot-dostoevsky` / `idiot-batuman`, `home-morrison` / `home-robinson`, `gift-hyde` / `gift-mauss` |
| Omnibus and its volumes | `lotr-omnibus`, `hdm-omnibus`, `earthsea-quartet`, `narnia-omnibus`, `sherlock-complete` |
| Substring titles | `it` / `it-ends-with-us`, `the-road` / `road-less-traveled`, `dune` / `dune-messiah` |
| Author name forms | `Tolkien, J. R. R.` / `JRR Tolkien`, `García Márquez` / `Garcia Marquez`, `Dostoevsky` / `Dostoyevsky` |

The second pass added 600 commonly owned titles, weighted toward what is
actually on shelves in Ontario: Canadian literary fiction and non-fiction,
Indigenous authors, mass-market thrillers, children's books, and classics. A
catalog of obscure titles matches nothing and proves nothing.

A third pass took it to 1,000 using published bestseller lists rather than
recall: the Publishers Weekly annual top-ten lists for 2010–2025 and the
Goodreads Choice Award winners across all categories for 2009–2025. Sourcing
them this way means every row is a real book that demonstrably sold, rather
than a title that merely sounds plausible.

That pass produced ambiguity on its own, which is the more convincing kind:
*Golden Son* (Pierce Brown) now collides with *The Golden Son* (Shilpi Somaya
Gowda), and *The Left Hand of Darkness* with *The Left Hand of God*.

The catalog is read into memory once per process rather than stored in SQLite.
At 1,000 rows that costs 1.4 ms at startup and keeps `matching.py` free of
Django imports, which is why the tests run in 0.09 s. Measured scaling: 0.23 ms
per match at 1,000 rows — 23 ms for a whole photo, against a VLM step measured
in seconds. At 5,000 rows it is 3.6 ms per match. Past roughly 20,000 this
would need a real index.

Size was capped at 1,000 deliberately. A larger catalog raises the hit rate but
also puts more near-neighbours inside the confidence margin, so more books land
in review. Rows that will never appear on a real shelf can only add ambiguity.

## Matching

Exact comparison fails on a catalog built to the spec above, so matching is a
scored pipeline.

1. **Normalize** — case, Unicode accents, punctuation, `&` → `and`, leading
   articles. Apostrophes are deleted rather than replaced, so `hitchhiker's`
   becomes `hitchhikers` and not `hitchhiker s`. `Last, First` is flipped
   before punctuation is stripped, since the comma is the only signal.
2. **Retrieve** — inverted index over title tokens and author surnames.
3. **Score** — best fuzzy similarity across the canonical title and every
   alternate, same for authors. Three corrections on top:
   - *Containment cap*: a title contained in a longer one is capped by how much
     of the longer title it covers, so `Road` cannot ride on
     `Road Less Traveled`. Skipped above 85% coverage so typos are not punished.
   - *Stopword gate*: if the meaningful words of two titles have nothing in
     common, the title score is capped at 0.45. Without it, "Song of the Sun
     God" scored 0.72 against "The Lord of the Rings" on the strength of "of
     the".
   - *Surname floor*: spines often print only a surname, so an exact surname
     hit floors the author score at 0.90.
4. **Blend** — 0.65 title, 0.35 author. A read with no author is discounted to
   0.90, since nothing corroborates it.
5. **Confidence** — the blended score adjusted by the margin to the runner-up.
   A 0.98 match with a 0.98 runner-up is ambiguous, not confident, and
   collapses toward the review band. This is what sends two editions of Dune to
   a human instead of resolving to whichever sorts first. Where the collision is
   an omnibus/volume pair or two editions, the reason is returned as text and
   shown in the review screen.

| Confidence | Status |
| --- | --- |
| ≥ 0.85 | `matched` |
| 0.55 – 0.85 | `review` |
| < 0.55 | `unmatched` |

Thresholds are configuration, not constants in the matcher.

### Tests

`backend/scanner/tests/test_matching.py`, 24 tests, asserting on routing rather
than float values so tuning weights does not require rewriting the suite. Each
planted ambiguity has a test, plus three for books that are *not* in the
catalog — the common case on a real shelf, and the one that found the stopword
bug.

## Failure handling

| Failure | Behaviour |
| --- | --- |
| VLM timeout | Retry with backoff, then mark those spines `unreadable` and return the rest |
| Malformed JSON | Parsed per item; bad entries become `unreadable`, batch still returns |
| Model omits a crop | That spine becomes `unreadable` rather than disappearing |
| Title but no author | Matched on title alone, reduced confidence, routed to review |
| Book not in the catalog | `unmatched`, with the raw read shown so it can be added by hand |
| Zero spines detected | "No books found" state with framing advice |
| Unreadable spine | `unreadable`, crop shown, user can type it in |
| No API key or network | Detection still runs, spines return `unreadable` with the reason |
| Over the per-scan read limit | Marked `skipped` and shown, never silently truncated |
| Backend unreachable | Retry offered, photo retained |

No detected spine is accepted or dropped without the user seeing it.

## Decisions and tradeoffs

**YOLOv8n over an open-vocabulary detector.** COCO's `book` class handles both
upright spines and books lying flat better than expected: 93 boxes on a shelf
of roughly that many books, in 3.5 s on CPU. Grounding DINO or OWL-ViT prompted with "book spine"
would fit the task better semantically but costs seconds per image. Measured
first, then chose.

**Confidence 0.22, from a sweep run twice.** The first sweep used only photos
of upright books and 0.25 looked right — it was where the curve bends
(shelf2: 0.15 → 98 boxes, 0.20 → 93, 0.25 → 82, 0.30 → 78, 0.35 → 70). Adding
a photo containing stacked books changed the answer, because flat books sit
lower in the detector's confidence distribution:

| conf | shelf2 | shelf3 | of which flat |
| --- | --- | --- | --- |
| 0.25 | 82 | 47 | 10 |
| 0.20 | 93 | 54 | 14 |
| 0.15 | 98 | 61 | 17 |
| 0.12 | 102 | 68 | 20 |

0.22 was chosen as the balance: it recovers most of the stacked books without
the fragment boxes that appear lower down.

**Crop rotation was the single biggest quality lever.** Rotated the wrong way,
reads came back as garbage — "DAVID BALDACCI" was read as "BRIGGSAM". The bug
was invisible in unit tests and obvious the moment the crops were looked at.

**Upscaling crops to 220px on the short edge.** Detected spines are often 40–60
px tall, too few pixels to resolve lettering. This costs ~7× the tokens per
spine. A crop the model cannot read costs the same and returns nothing.

**Reads run concurrently.** Five batches in flight at once, set by
`VLM_CONCURRENCY`. Measured before and after on the same photo: reads dropped
from 39.8 s to 9.4 s and the scan from 48.7 s to 18.0 s, with input tokens
unchanged at 28,485. Results are reassembled by batch offset rather than in
completion order, so spine order is preserved.

**Matching is deterministic and local.** Slower to tune than asking a model to
pick, but free, explicable, and testable — and the brief asks how the
confidence score is arrived at.

**Per-scan read limit.** `VLM_MAX_SPINES` caps paid reads per photo. Spines
past the cap are returned as `skipped` rather than dropped, so the ceiling is
visible in the UI.

**SQLite, no auth, single user.** Neither is graded, and this is the honest
scope for the time budget.

## Unfinished

- **Stacked books are detected, but coverage varies with the threshold.**
  `shelf3.jpeg` yields 12 flat boxes at 0.22, 14 at 0.20 and 10 at 0.25, out of
  52 boxes total. The misses are books deep in a stack where only a sliver of
  spine is visible. Crops of stacked books often include
  the neighbours above and below, since the boxes overlap vertically; the
  prompt asks for the middle book, which mostly works.
- **Not verified on a physical device.** The project is on Expo SDK 57, which is
  newer than the SDK supported by the Expo Go build currently in the App Store,
  so the QR code route is unavailable.

## What I'd do with another day

- Add duplicate detection, so a book already in the library is flagged at scan
  time instead of being added twice.
- Test against a wider variety of bookshelf photos, at different angles and in
  different lighting.
- Improve the UI.
- Add the option to rerun your low confidence reads a second time.
- Test mobile functionality.

## AI usage

See [AI_USAGE.md](./AI_USAGE.md).
