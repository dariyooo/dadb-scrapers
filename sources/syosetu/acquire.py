"""Syosetu crawler — stage 1: raw HTML dump.

Discovers works via the official API (no selectors to go stale) and enumerates
chapter URLs from its chapter counts. Resumable across CI runs via committed
state/ (works.json + cursor.json); --max-seconds stops cleanly before the job cap.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, TypeAdapter

from core.docjson import BatchWriter, make_doc
from core.fetch import Blocked, Fetcher, NotFound

log = logging.getLogger("syosetu.acquire")

HERE = Path(__file__).parent
API_PAGE_SIZE = 500


class Work(BaseModel):
    ncode: str
    title: str
    writer: str
    chapters: int
    short: bool


class Cursor(BaseModel):
    work_index: int = 0
    chapter: int = 1


WORK_LIST = TypeAdapter(list[Work])


def load_config() -> dict[str, Any]:
    return yaml.safe_load((HERE / "config.yaml").read_text())


def discover(fetcher: Fetcher, cfg: dict[str, Any]) -> list[Work]:
    """Enumerate top works via the novel API."""
    api = cfg["api"]
    works: list[Work] = []
    st = 1
    while len(works) < api["max_works"] and st <= 2000:
        url = (
            f"{api['endpoint']}?out=json&of=t-n-w-ga-nt"
            f"&order={api['order']}&lim={API_PAGE_SIZE}&st={st}"
        )
        rows = fetcher.get(url).json()
        allcount = rows[0]["allcount"]
        works.extend(
            Work(
                ncode=row["ncode"].lower(),
                title=row["title"],
                writer=row["writer"],
                chapters=row["general_all_no"],
                short=row["noveltype"] == 2,
            )
            for row in rows[1:]
        )
        if st + API_PAGE_SIZE > allcount:
            break
        st += API_PAGE_SIZE
    return works[: api["max_works"]]


def chapter_url(work: Work, chapter: int) -> str:
    base = f"https://ncode.syosetu.com/{work.ncode}/"
    return base if work.short else f"{base}{chapter}/"


def crawl(
    fetcher: Fetcher,
    works: list[Work],
    cursor: Cursor,
    writer: BatchWriter,
    deadline: float,
    max_pages: int,
) -> Cursor:
    """Fetch chapters from the cursor until deadline/limit/done; returns the cursor."""
    pages = 0
    while cursor.work_index < len(works):
        work = works[cursor.work_index]
        total = 1 if work.short else work.chapters
        while cursor.chapter <= total:
            if time.monotonic() >= deadline:
                log.info("time budget reached at %s ch%d", work.ncode, cursor.chapter)
                return cursor
            if max_pages and pages >= max_pages:
                log.info("page limit reached at %s ch%d", work.ncode, cursor.chapter)
                return cursor
            url = chapter_url(work, cursor.chapter)
            try:
                resp = fetcher.get(url)
            except NotFound:
                log.warning("gone, skipping rest of work: %s", url)
                break
            writer.write(make_doc(url, f"{work.title} #{cursor.chapter}", resp.text))
            pages += 1
            cursor.chapter += 1
        cursor.work_index += 1
        cursor.chapter = 1
    log.info("work list exhausted")
    return cursor


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="out", help="batch output directory")
    ap.add_argument("--state", default=str(HERE / "state"), help="cursor/works dir")
    ap.add_argument("--max-seconds", type=float, default=19200)
    ap.add_argument("--max-pages", type=int, default=0, help="0 = unlimited")
    ap.add_argument("--rediscover", action="store_true", help="refresh works.json")
    args = ap.parse_args()

    cfg = load_config()
    fetcher = Fetcher(min_interval=cfg["rate_limit_seconds"])
    state = Path(args.state)
    state.mkdir(parents=True, exist_ok=True)
    works_path = state / "works.json"
    cursor_path = state / "cursor.json"

    if args.rediscover or not works_path.exists():
        log.info("discovering works via API")
        works = discover(fetcher, cfg)
        works_path.write_bytes(WORK_LIST.dump_json(works, indent=1))
        cursor_path.write_text(Cursor().model_dump_json())
        log.info("discovered %d works", len(works))

    works = WORK_LIST.validate_json(works_path.read_bytes())
    cursor = Cursor.model_validate_json(cursor_path.read_text())
    if cursor.work_index >= len(works):
        log.info("crawl already complete (%d works)", len(works))
        return 0

    deadline = time.monotonic() + args.max_seconds
    blocked = False
    with BatchWriter(args.out, cfg["site"]) as writer:
        try:
            cursor = crawl(fetcher, works, cursor, writer, deadline, args.max_pages)
        except Blocked as e:
            log.error("site is refusing us, aborting run: %s", e)
            blocked = True
        finally:
            cursor_path.write_text(cursor.model_dump_json())
            log.info(
                "wrote %d docs to %s; cursor at work %d/%d",
                writer.count,
                writer.path,
                cursor.work_index,
                len(works),
            )
    return 2 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
