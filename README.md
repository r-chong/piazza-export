# Piazza Rescue

Local-only Piazza archiver built for time-sensitive course exports. It uses your existing Piazza browser session, saves full raw post JSON, downloads PDF attachments, extracts PDF text, and builds a SQLite FTS index for keyword search.

## What It Produces

Each run creates a dated directory under `archive/`, for example:

```text
archive/example123456-20260415T182300Z/
  browser/
  attachments/
  attachments_manifest.jsonl
  class.json
  failures.jsonl
  feed.json
  manifest.json
  pdf_docs.jsonl
  posts.jsonl
  preflight_post.json
  search.db
  search_docs.jsonl
  stats.json
```

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Authentication

Preferred option on macOS: read cookies directly from a logged-in browser profile.

```bash
piazza-rescue archive example123456 --browser chrome --preflight-post 327
```

Supported browser names: `chrome`, `chromium`, `brave`, `edge`, `firefox`, `opera`, `vivaldi`, `safari`.

Manual cookie input is also supported:

```bash
piazza-rescue archive example123456 \
  --cookie-file piazza-cookies.json \
  --preflight-post 327
```

Cookie files may be:

- A JSON object like `{"session_id": "...", "piazza_session": "..."}`
- A JSON list exported by browser cookie tools
- A raw `Cookie:` header string

Important: Piazza's `session_id` cookie is `HttpOnly`, so `document.cookie` is not sufficient. If you are not using `--browser`, export cookies from the browser's storage/devtools panel or a cookie-export tool that includes `HttpOnly` cookies.

## Run The Export

```bash
piazza-rescue archive example123456 \
  --browser chrome \
  --preflight-post 327 \
  --sleep 1 \
  --download-pdfs
```

Useful flags:

- `--limit 25`: export a small sample first
- `--output-root /path/to/archive-root`: change where archives are stored
- `--cookie-string 'session_id=...; piazza_session=...'`: paste cookie header values directly
- `--no-download-pdfs`: keep attachment metadata only
- `--no-extract-pdf-text`: skip `pdftotext`
- `--no-build-search-db`: skip SQLite index creation

## Search The Archive

Search posts:

```bash
piazza-rescue search archive/example123456-20260415T182300Z/search.db "midterm 1" --label midterm_1
```

View a result by post number:

```bash
piazza-rescue show archive/example123456-20260415T182300Z 327
piazza-rescue show archive/example123456-20260415T182300Z/search.db 327
```

Generate a simple static HTML browser:

```bash
piazza-rescue render-html archive/example123456-20260415T182300Z
open archive/example123456-20260415T182300Z/browser/index.html
```

Build all archive browsers at once and generate a master sitemap:

```bash
piazza-rescue render-html-all archive
open archive/index.html
```

Search PDFs:

```bash
piazza-rescue search archive/example123456-20260415T182300Z/search.db "lecture notes" --source pdf
```

Filter examples:

```bash
piazza-rescue search archive/.../search.db "final" --label final --has-pdf
piazza-rescue search archive/.../search.db "hw9" --folder hw9
piazza-rescue show archive/.../search.db 321
```

## Search And RAG Notes

- Immediate local keyword search is handled by `search.db`, backed by SQLite FTS5.
- `search_docs.jsonl` contains normalized post records ready for later import into Elasticsearch/OpenSearch if you ever want a heavier search stack.
- `pdf_docs.jsonl` contains extracted text from downloaded PDFs, which can be chunked and embedded later for RAG without touching Piazza again.
