"""Stage 1 -> 2 contract: doc JSON batched as {site}/{timestamp}.jsonl.zst.

Raw HTML is kept verbatim so reparsing never requires re-crawling.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import zstandard
from pydantic import BaseModel


class Doc(BaseModel):
    format: str = "html"  # picks the parser
    source: str  # picks the config
    lang: str = "ja"
    url: str
    title: str
    created: str
    published: str | None = None
    text: str


def make_doc(source: str, url: str, title: str, html: str, published: str | None = None) -> Doc:
    return Doc(
        source=source,
        url=url,
        title=title,
        created=datetime.now(UTC).isoformat(timespec="seconds"),
        published=published,
        text=html,
    )


class BatchWriter:
    """Streams doc JSON records into out_dir/{site}/{timestamp}.jsonl.zst."""

    def __init__(self, out_dir: str | Path, site: str):
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.path = Path(out_dir) / site / f"{stamp}.jsonl.zst"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.count = 0
        self._fh = open(self.path, "wb")  # noqa: SIM115 — closed in close()
        self._writer = zstandard.ZstdCompressor(level=10).stream_writer(self._fh)

    def write(self, doc: Doc) -> None:
        self._writer.write(doc.model_dump_json().encode("utf-8") + b"\n")
        self.count += 1

    def close(self) -> Path:
        self._writer.close()
        self._fh.close()
        if self.count == 0:
            self.path.unlink()
        return self.path

    def __enter__(self) -> BatchWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_batch(path: str | Path) -> Iterator[Doc]:
    """Yield Doc records from a .jsonl.zst batch."""
    with open(path, "rb") as fh:
        reader = zstandard.ZstdDecompressor().stream_reader(fh)
        buf = b""
        while True:
            chunk = reader.read(1 << 20)
            if not chunk:
                break
            buf += chunk
            while (nl := buf.find(b"\n")) >= 0:
                line, buf = buf[:nl], buf[nl + 1 :]
                if line.strip():
                    yield Doc.model_validate_json(line)
        if buf.strip():
            yield Doc.model_validate_json(buf)
