import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from core.docjson import BatchWriter
from core.fetch import Fetcher
from sources.syosetu.acquire import (
    Cursor,
    PassState,
    Work,
    chapter_url,
    coordinate,
    crawl,
    cursor_path,
    start_new_pass,
)

CFG = {"shards": 3, "pass_interval_days": 55, "heartbeat_days": 14}
NOW = datetime(2026, 7, 30, 12, 0, 0, tzinfo=UTC)


def works(n: int) -> list[Work]:
    return [
        Work(ncode=f"n{i:07d}", title=f"作品{i}", writer="w", chapters=2, short=False)
        for i in range(n)
    ]


class FakeResponse:
    text = "<html>ページ</html>"


class FakeFetcher:
    """Duck-typed stand-in; cast to Fetcher at call sites."""

    def __init__(self):
        self.urls: list[str] = []

    def get(self, url: str) -> FakeResponse:
        self.urls.append(url)
        return FakeResponse()


def read_pass(state: Path) -> PassState:
    return PassState.model_validate_json((state / "pass.json").read_text())


def complete_all_shards(state: Path, works_len: int) -> None:
    for shard in range(CFG["shards"]):
        cursor_path(state, shard).write_text(Cursor(work_index=works_len + shard).model_dump_json())


class TestCoordinate:
    def test_first_run_starts_pass(self, tmp_path):
        assert coordinate(tmp_path, CFG, lambda: works(6), NOW) == "crawl"
        assert read_pass(tmp_path).completed is None
        for shard in range(3):
            cursor = Cursor.model_validate_json(cursor_path(tmp_path, shard).read_text())
            assert cursor == Cursor(work_index=shard, chapter=1)

    def test_mid_pass_keeps_crawling(self, tmp_path):
        coordinate(tmp_path, CFG, lambda: works(6), NOW)
        assert coordinate(tmp_path, CFG, lambda: works(6), NOW) == "crawl"

    def test_completion_then_idle(self, tmp_path):
        coordinate(tmp_path, CFG, lambda: works(6), NOW)
        complete_all_shards(tmp_path, 6)
        assert coordinate(tmp_path, CFG, lambda: works(6), NOW) == "idle"
        assert read_pass(tmp_path).completed is not None
        assert coordinate(tmp_path, CFG, lambda: works(6), NOW) == "idle"

    def test_new_pass_after_interval(self, tmp_path):
        coordinate(tmp_path, CFG, lambda: works(6), NOW)
        complete_all_shards(tmp_path, 6)
        coordinate(tmp_path, CFG, lambda: works(6), NOW)
        later = NOW + timedelta(days=56)
        assert coordinate(tmp_path, CFG, lambda: works(6), later) == "crawl"
        assert read_pass(tmp_path).completed is None

    def test_idle_heartbeat_refreshes(self, tmp_path):
        coordinate(tmp_path, CFG, lambda: works(6), NOW)
        complete_all_shards(tmp_path, 6)
        coordinate(tmp_path, CFG, lambda: works(6), NOW)
        later = NOW + timedelta(days=20)
        assert coordinate(tmp_path, CFG, lambda: works(6), later) == "idle"
        assert read_pass(tmp_path).heartbeat == later.isoformat(timespec="seconds")

    def test_new_pass_removes_legacy_cursor(self, tmp_path):
        (tmp_path / "cursor.json").write_text("{}")
        start_new_pass(tmp_path, works(3), 3, NOW)
        assert not (tmp_path / "cursor.json").exists()


class TestShardCrawl:
    def test_shard_takes_every_third_work(self, tmp_path):
        all_works = works(6)
        fetcher = FakeFetcher()
        with BatchWriter(tmp_path, "syosetu") as writer:
            cursor = crawl(
                cast(Fetcher, fetcher),
                all_works,
                Cursor(work_index=1),
                3,
                writer,
                deadline=1e18,
                max_pages=0,
            )
            assert writer.count == 4  # works 1 and 4, 2 chapters each
        assert cursor.work_index == 7
        expected = [chapter_url(all_works[i], ch) for i in (1, 4) for ch in (1, 2)]
        assert fetcher.urls == expected

    def test_page_limit_saves_position(self, tmp_path):
        fetcher = FakeFetcher()
        with BatchWriter(tmp_path, "syosetu") as writer:
            cursor = crawl(
                cast(Fetcher, fetcher),
                works(6),
                Cursor(work_index=0),
                3,
                writer,
                deadline=1e18,
                max_pages=3,
            )
        assert (cursor.work_index, cursor.chapter) == (3, 2)


def test_pass_label(tmp_path):
    from core.summary import pass_label

    pass_file = tmp_path / "pass.json"
    pass_file.write_text(json.dumps({"started": "2026-08-01T02:00:00+00:00"}))
    assert pass_label(pass_file) == "2026-08"


def test_chunk_tag_and_manifest():
    from core.publish import chunk_tag

    assert chunk_tag("2026-08", 0) == "2026-08.1"
    assert chunk_tag("2026-08", 499) == "2026-08.1"
    assert chunk_tag("2026-08", 500) == "2026-08.2"
    assert chunk_tag("2026-08", 1999) == "2026-08.4"


def test_build_manifest(tmp_path):
    from core.publish import build_manifest

    works_path = tmp_path / "works.json"
    works_path.write_text(
        json.dumps(
            [
                {"ncode": f"n{i}", "title": f"t{i}", "writer": "w", "chapters": 1, "short": False}
                for i in range(600)
            ]
        )
    )
    stats = {
        "works": {
            "n0": {
                "title": "t0",
                "chapters": 1,
                "sentences": 5,
                "bytes": 9,
                "sha256": "aa",
                "revision": "r",
            },
            "n599": {
                "title": "t599",
                "chapters": 1,
                "sentences": 3,
                "bytes": 4,
                "sha256": "bb",
                "revision": "r",
            },
        }
    }
    m = build_manifest(stats, works_path, "2026-08", "o/r", "syosetu")
    assert m["pass"] == "2026-08"
    urls = {e["ncode"]: e["url"] for e in m["works"]}
    assert "2026-08.1" in urls["n0"]
    assert "2026-08.2" in urls["n599"]
    assert m["works"][0]["writer"] == "w"


def test_stats_merge_accumulates_across_runs(tmp_path):
    from core.summary import merge

    stats = tmp_path / "stats"
    build_a = tmp_path / "a.json"
    build_b = tmp_path / "b.json"
    build_a.write_text(
        json.dumps(
            [
                {"id": "n1", "title": "一", "url": "u", "chapters": 2, "sentences": 10, "bytes": 5},
                {"id": "n2", "title": "二", "url": "u", "chapters": 1, "sentences": 4, "bytes": 2},
            ]
        )
    )
    build_b.write_text(
        json.dumps(
            [{"id": "n3", "title": "三", "url": "u", "chapters": 1, "sentences": 6, "bytes": 3}]
        )
    )
    result = merge(stats, "syosetu", "2026-08", [build_a, build_b])
    assert result == {"merged": 3, "works": 3, "sentences": 20, "bytes": 10}

    # next run updates one work and adds another
    build_c = tmp_path / "c.json"
    build_c.write_text(
        json.dumps(
            [
                {"id": "n1", "title": "一", "url": "u", "chapters": 3, "sentences": 12, "bytes": 6},
                {"id": "n4", "title": "四", "url": "u", "chapters": 1, "sentences": 1, "bytes": 1},
            ]
        )
    )
    result = merge(stats, "syosetu", "2026-08", [build_c])
    assert result == {"merged": 2, "works": 4, "sentences": 23, "bytes": 12}
    summary = json.loads((stats / "syosetu-2026-08.json").read_text())
    assert summary["works"]["n1"]["sentences"] == 12
