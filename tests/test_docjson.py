import pytest
from pydantic import ValidationError

from core.docjson import BatchWriter, Doc, make_doc, read_batch


def test_round_trip(tmp_path):
    doc = make_doc("syosetu", "https://example.com/n1/1/", "作品 #1", "<html>本文</html>")
    assert doc.format == "html"
    assert doc.source == "syosetu"

    with BatchWriter(tmp_path, "syosetu") as writer:
        writer.write(doc)
        path = writer.path

    docs = list(read_batch(path))
    assert len(docs) == 1
    assert docs[0] == doc


def test_source_is_required():
    with pytest.raises(ValidationError):
        Doc(url="u", title="t", created="c", text="x")  # type: ignore[call-arg]


def test_empty_batch_file_is_removed(tmp_path):
    with BatchWriter(tmp_path, "syosetu") as writer:
        path = writer.path
    assert not path.exists()
