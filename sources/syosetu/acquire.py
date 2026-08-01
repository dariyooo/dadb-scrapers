"""Syosetu crawler — stage 1: raw HTML dump.

Discovers works via the official API and enumerates chapter URLs from its
chapter counts. Crawling runs in shards (worker i takes works where
index % shards == i) as endless passes: crawl the full list, idle for
pass_interval_days, re-discover, repeat. --coordinate decides the phase and
owns discovery; state/ is committed between CI runs.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import UTC, datetime, timedelta
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
    work_index: int
    chapter: int = 1


class PassState(BaseModel):
    started: str
    completed: str | None = None
    heartbeat: str | None = None


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


def cursor_path(state: Path, shard: int) -> Path:
    return state / f"cursor-{shard}.json"


def _now_iso(now: datetime) -> str:
    return now.isoformat(timespec="seconds")


def start_new_pass(state: Path, works: list[Work], num_shards: int, now: datetime) -> None:
    (state / "works.json").write_bytes(WORK_LIST.dump_json(works, indent=1))
    for shard in range(num_shards):
        cursor_path(state, shard).write_text(Cursor(work_index=shard).model_dump_json())
    (state / "pass.json").write_text(PassState(started=_now_iso(now)).model_dump_json())
    (state / "cursor.json").unlink(missing_ok=True)  # pre-shard layout
    log.info("new pass started: %d works, %d shards", len(works), num_shards)


def shard_complete(state: Path, shard: int, works_len: int) -> bool:
    path = cursor_path(state, shard)
    if not path.exists():
        return False
    return Cursor.model_validate_json(path.read_text()).work_index >= works_len


def coordinate(state: Path, cfg: dict[str, Any], discover_works, now: datetime) -> str:
    """Advance the pass lifecycle; returns 'crawl' or 'idle'."""
    num_shards = cfg["shards"]
    pass_path = state / "pass.json"
    if not pass_path.exists():
        start_new_pass(state, discover_works(), num_shards, now)
        return "crawl"

    p = PassState.model_validate_json(pass_path.read_text())
    works_len = len(WORK_LIST.validate_json((state / "works.json").read_bytes()))
    if not all(shard_complete(state, s, works_len) for s in range(num_shards)):
        return "crawl"

    if p.completed is None:
        p.completed = p.heartbeat = _now_iso(now)
        pass_path.write_text(p.model_dump_json())
        log.info("pass completed")
        return "idle"

    if now - datetime.fromisoformat(p.completed) >= timedelta(days=cfg["pass_interval_days"]):
        start_new_pass(state, discover_works(), num_shards, now)
        return "crawl"

    # Idle: refresh the heartbeat periodically so the committed state change
    # keeps GitHub from auto-disabling the cron after 60 days of inactivity.
    last_beat = datetime.fromisoformat(p.heartbeat or p.completed)
    if now - last_beat >= timedelta(days=cfg["heartbeat_days"]):
        p.heartbeat = _now_iso(now)
        pass_path.write_text(p.model_dump_json())
        log.info("heartbeat")
    return "idle"


def crawl(
    fetcher: Fetcher,
    works: list[Work],
    cursor: Cursor,
    num_shards: int,
    writer: BatchWriter,
    deadline: float,
    max_pages: int,
    max_works: int = 0,
) -> Cursor:
    """Fetch this shard's chapters from the cursor until deadline/limit/done."""
    pages = 0
    works_done = 0
    while cursor.work_index < len(works):
        if max_works and works_done >= max_works:
            log.info("work limit reached")
            return cursor
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
            writer.write(make_doc("syosetu", url, f"{work.title} #{cursor.chapter}", resp.text))
            pages += 1
            cursor.chapter += 1
        cursor.work_index += num_shards
        cursor.chapter = 1
        works_done += 1
    log.info("shard slice exhausted")
    return cursor


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--coordinate", action="store_true", help="advance pass lifecycle")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--out", default="out", help="batch output directory")
    ap.add_argument("--state", default=str(HERE / "state"), help="state dir")
    ap.add_argument("--max-seconds", type=float, default=19200)
    ap.add_argument("--max-pages", type=int, default=0, help="0 = unlimited")
    ap.add_argument(
        "--max-works", type=int, default=0, help="complete works per run, 0 = unlimited"
    )
    args = ap.parse_args()

    cfg = load_config()
    fetcher = Fetcher(min_interval=cfg["rate_limit_seconds"])
    state = Path(args.state)
    state.mkdir(parents=True, exist_ok=True)

    if args.coordinate:
        pass_path = state / "pass.json"

        def completed() -> str | None:
            if not pass_path.exists():
                return None
            return PassState.model_validate_json(pass_path.read_text()).completed

        before = completed()
        phase = coordinate(state, cfg, lambda: discover(fetcher, cfg), datetime.now(UTC))
        just_completed = before is None and completed() is not None
        outputs = f"phase={phase}\npass_completed={str(just_completed).lower()}\n"
        print(outputs, end="")
        if out_path := os.environ.get("GITHUB_OUTPUT"):
            with open(out_path, "a") as fh:
                fh.write(outputs)
        return 0

    works = WORK_LIST.validate_json((state / "works.json").read_bytes())
    cpath = cursor_path(state, args.shard)
    cursor = Cursor.model_validate_json(cpath.read_text())
    if cursor.work_index >= len(works):
        log.info("shard %d already complete", args.shard)
        return 0

    deadline = time.monotonic() + args.max_seconds
    blocked = False
    with BatchWriter(args.out, cfg["site"]) as writer:
        try:
            cursor = crawl(
                fetcher,
                works,
                cursor,
                cfg["shards"],
                writer,
                deadline,
                args.max_pages,
                args.max_works,
            )
        except Blocked as e:
            log.error("site is refusing us, aborting run: %s", e)
            blocked = True
        finally:
            cpath.write_text(cursor.model_dump_json())
            log.info(
                "wrote %d docs to %s; shard %d cursor at %d/%d",
                writer.count,
                writer.path,
                args.shard,
                cursor.work_index,
                len(works),
            )
    return 2 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
