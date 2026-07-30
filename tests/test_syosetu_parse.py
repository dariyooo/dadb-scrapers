from pathlib import Path

import pytest

from sources.syosetu.parse import ParseError, chapter_text, parse_chapter

FIXTURES = Path(__file__).parent / "fixtures" / "syosetu"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestRealChapter:
    """n2267be_1.html — Re:Zero prologue, live markup as of 2026-07."""

    def test_title(self):
        parsed = parse_chapter(load("n2267be_1.html"))
        assert parsed.title == "プロローグ　『始まりの余熱』"

    def test_body(self):
        text = chapter_text(parse_chapter(load("n2267be_1.html")))
        assert "――これは本気でヤバい。" in text
        assert "叫び声を上げようと口を開いた瞬間" in text
        assert len(text.splitlines()) > 30
        assert "<" not in text

    def test_no_page_furniture(self):
        text = chapter_text(parse_chapter(load("n2267be_1.html")))
        assert "しおり" not in text
        assert "ログイン" not in text


class TestAfterword:
    """n3009bk_1.html — Overlord ch1, has a real afterword block."""

    def test_afterword_excluded(self):
        text = chapter_text(parse_chapter(load("n3009bk_1.html")))
        assert text
        assert "初めに読んでいただきありがとうございます" not in text


@pytest.fixture(scope="module")
def parsed():
    return parse_chapter(load("synthetic_ruby.html"))


class TestRubyAndNotes:
    """synthetic_ruby.html — every ruby form plus preface/afterword."""

    def test_title_ruby_stripped(self, parsed):
        assert parsed.title == "第一話　竜の朝"

    def test_html_ruby_with_rb(self, parsed):
        assert "魔法を使う。" in parsed.paragraphs

    def test_html_ruby_without_rb(self, parsed):
        assert "竜が来た。" in parsed.paragraphs

    def test_marked_text_ruby(self, parsed):
        assert "勇者は「無敵」だ。" in parsed.paragraphs

    def test_bare_text_ruby_vs_emphasis(self, parsed):
        # 漢字《かんじ》 is ruby (kanji base + kana reading) -> stripped;
        # 《強調》 is emphasis -> kept.
        assert "漢字と《強調》は違う。" in parsed.paragraphs

    def test_notes_excluded(self, parsed):
        text = chapter_text(parsed)
        assert "前書き" not in text
        assert "後書き" not in text

    def test_blank_runs_collapse(self, parsed):
        assert "\n\n\n" not in chapter_text(parsed)


class TestSelectorRot:
    def test_unrecognized_markup_is_loud(self):
        with pytest.raises(ParseError):
            parse_chapter("<html><body><p>not syosetu</p></body></html>")
