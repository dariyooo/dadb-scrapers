# dadb-scrapers

Scrapers and parsers producing Japanese example-sentence source dumps for DaDb.

## Pipeline

```text
acquire (per site)  → raw site dump        {site}/{ISO8601}.jsonl.zst
parse   (per site)  → clean per-work .txt  {ncode}.txt + {ncode}.json
pack                → DaDb Example Texts zips (later stage)
```

Raw dumps keep the fetched HTML verbatim, so reparsing never requires
re-crawling. Each crawl run publishes its dump as a GitHub Release.

## Layout

```text
sources/{site}/   config.yaml + acquire.py + parse.py + state/
core/             fetch (rate limit, retry), doc JSON batch I/O
tests/            parser tests + fixtures/{site}/
.github/workflows/crawl.yml   6 h cron, resumable via committed cursor
```

## Running locally

```sh
uv sync
uv run pytest && uv run ruff check . && uv run pyright
uv run python -m sources.syosetu.acquire --out out --max-pages 10
uv run python -m sources.syosetu.parse out/syosetu/*.jsonl.zst --out out/text
```

Crawling is rate-limited per site (3 s/request, backoff, hard stop on 403).
Never run two crawlers against the same site at once.
