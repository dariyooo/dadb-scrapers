"""Syosetu parser — stage 2: raw HTML dump -> clean per-work .txt.

Strips ruby (markup and text forms) and preface/afterword using the 2022+
ncode markup; raises ParseError on unexpected structure so selector rot is loud.
Pure-text cleaning (splitting, normalization, quality gating) is the importer's job.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup
from pydantic import BaseModel

from core.docjson import read_batch

log = logging.getLogger("syosetu.parse")


class WorkMeta(BaseModel):
    url: str
    title: str = ""
    chapters: int = 0


class Chapter(BaseModel):
    title: str
    paragraphs: list[str]  # "" = author blank line


URL_RE = re.compile(r"ncode\.syosetu\.com/(n[0-9a-z]+)/(?:(\d+)/)?")

# ｜base《reading》 — explicit ruby marker, always stripped.
MARKED_RUBY_RE = re.compile(r"[｜|]([^《｜|]+)《[^》]+》")
# kanji《kana》 only, so 《emphasis》 survives.
BARE_RUBY_RE = re.compile(r"([一-鿿々〆ヶ]+)《[ぁ-ゖァ-ヺー・゙゚]+》")


class ParseError(Exception):
    """Page didn't match the expected syosetu markup — selectors went stale."""


def strip_text_ruby(text: str) -> str:
    text = MARKED_RUBY_RE.sub(r"\1", text)
    return BARE_RUBY_RE.sub(r"\1", text)


def _body_paragraphs(div) -> list[str]:
    """Paragraph texts from a p-novel__text div; '' for blank-line <p>s."""
    for tag in div.find_all(["rt", "rp"]):
        tag.decompose()
    for tag in div.find_all(["ruby", "rb"]):
        tag.unwrap()
    out = []
    for p in div.find_all("p"):
        out.append(strip_text_ruby(p.get_text()).strip("　").strip())
    return out


def parse_chapter(html: str) -> Chapter:
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.select_one("h1.p-novel__title")
    if title_el is None:
        raise ParseError("h1.p-novel__title not found")
    bodies = soup.select(
        "div.js-novel-text.p-novel__text"
        ":not(.p-novel__text--preface):not(.p-novel__text--afterword)"
    )
    if len(bodies) != 1:
        raise ParseError(f"expected 1 main text div, found {len(bodies)}")
    return Chapter(
        title=strip_text_ruby(title_el.get_text()).strip(),
        paragraphs=_body_paragraphs(bodies[0]),
    )


def chapter_text(parsed: Chapter) -> str:
    """Join paragraphs, collapsing blank runs to a single blank line."""
    lines: list[str] = []
    for para in parsed.paragraphs:
        if para:
            lines.append(para)
        elif lines and lines[-1] != "":
            lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def parse_batches(batch_paths: list[Path], out_dir: Path) -> dict[str, int]:
    """Emit {ncode}.txt + {ncode}.json per work. Returns stats."""
    chapters: dict[str, dict[int, str]] = {}
    meta: dict[str, WorkMeta] = {}
    errors = 0
    for path in batch_paths:
        for doc in read_batch(path):
            m = URL_RE.search(doc.url)
            if not m:
                raise ParseError(f"unrecognized URL: {doc.url}")
            ncode, chapter = m.group(1), int(m.group(2) or 1)
            try:
                parsed = parse_chapter(doc.text)
            except ParseError as e:
                log.error("%s: %s", doc.url, e)
                errors += 1
                continue
            chapters.setdefault(ncode, {})[chapter] = chapter_text(parsed)
            meta.setdefault(ncode, WorkMeta(url=f"https://ncode.syosetu.com/{ncode}/"))
            meta[ncode].title = doc.title.rsplit(" #", 1)[0]

    out_dir.mkdir(parents=True, exist_ok=True)
    for ncode, by_num in chapters.items():
        text = "\n\n".join(by_num[n] for n in sorted(by_num))
        (out_dir / f"{ncode}.txt").write_text(text + "\n", encoding="utf-8")
        meta[ncode].chapters = len(by_num)
        (out_dir / f"{ncode}.json").write_bytes(meta[ncode].model_dump_json(indent=1).encode())
    return {"works": len(chapters), "errors": errors}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("batches", nargs="+", help=".jsonl.zst batch files")
    ap.add_argument("--out", default="out/text/syosetu")
    args = ap.parse_args()
    stats = parse_batches([Path(p) for p in args.batches], Path(args.out))
    log.info("%s", stats)
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
