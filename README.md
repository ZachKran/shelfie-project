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
python manage.py runserver 0.0.0.0:8000
```

### Frontend

```bash
cd frontend
npm install
npx expo start
```

```
# frontend/.env
EXPO_PUBLIC_API_BASE_URL=http://<your-lan-ip>:8000
```

### Tests

```bash
cd backend && pytest
```

## Architecture

TODO

## Local vs hosted

| | Where |
| --- | --- |
| Spine detection | Local, CPU |
| Reading title/author off a spine | Hosted (Claude vision) |
| Catalog matching | Local |

TODO — why.

### Latency

| Stage | Median |
| --- | --- |
| Spine detection | — |
| VLM read | — |
| Matching | — |
| End to end | — |

### Cost per image

TODO

## Catalog

`catalog.csv` — TODO entries.

| Column | Notes |
| --- | --- |
| `title` | Canonical title |
| `author` | Canonical author |
| `alt_titles` | Pipe-separated alternates |

Planted ambiguities: two editions of one book, one book under US/UK titles, two
different books sharing a title, an omnibus alongside its volumes, substring
titles, author names in multiple forms.

TODO — how it was built.

## Matching

TODO

| Confidence | Status |
| --- | --- |
| ≥ TODO | `matched` |
| TODO – TODO | `review` |
| < TODO | `unmatched` |

## Failure handling

| Failure | Behaviour |
| --- | --- |
| VLM timeout | Retry with backoff, then mark those spines `unreadable` and return the rest |
| Malformed JSON | Parsed per item; bad entries become `unreadable`, batch still returns |
| Title but no author | Matched on title alone, reduced confidence, routed to review |
| Zero spines detected | "No books found" state with a retake prompt |
| Unreadable spine | Returned as `unreadable` with the crop, user can type it in |
| No API key or network | Detection still runs, spines return `unreadable` with the reason |
| Image too large | Downscaled server-side |
| Backend unreachable | Retry offered, photo retained |

No detected spine is accepted or dropped without the user seeing it.

## Decisions and tradeoffs

TODO

## Unfinished

TODO

## AI usage

See [AI_USAGE.md](./AI_USAGE.md).
