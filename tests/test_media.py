import json

from anicapshelf.media import clean_caption_text, normalize_search_text, parse_srt, stream_to_json


def test_clean_caption_text_removes_ruby_and_style_tags():
    raw = (
        '<font face="sans-serif" size="36">{\\an7}'
        '<font size="18"><font color="#00ff00">そこうしゃ</font></font>'
        '<font color="#00ff00">(キュゥべえ)時間遡行者 暁美ほむら｡</font></font>'
    )

    assert clean_caption_text(raw) == "(キュゥべえ)時間遡行者 暁美ほむら｡"


def test_normalize_search_text_folds_width_and_punctuation():
    assert normalize_search_text("ＭＡＧＩＡ・第５話　「約束」") == "MAGIA 第5話 約束"


def test_parse_srt_drops_empty_cues_and_bogus_long_end_time():
    raw = """1
00:00:11,361 --> 1193:02:58,656
<font face="sans-serif" size="36"></font>

2
00:00:13,663 --> 1193:03:00,958
<font face="sans-serif" size="36">{\\an7}<font size="18"><font color="#00ff00">そこうしゃ</font></font><font color="#00ff00">時間遡行者 暁美ほむら｡</font></font>
"""

    rows = parse_srt(raw)

    assert len(rows) == 1
    assert rows[0]["start"] == 13.663
    assert rows[0]["end"] is None
    assert rows[0]["text"] == "時間遡行者 暁美ほむら｡"


def test_stream_to_json_preserves_japanese_text():
    raw = stream_to_json({"index": 2, "codec_name": "arib_caption", "title": "字幕"})

    assert json.loads(raw)["title"] == "字幕"
