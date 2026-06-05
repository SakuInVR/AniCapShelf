from anicapshelf.media import clean_caption_text, parse_srt


def test_clean_caption_text_removes_ruby_and_style_tags():
    raw = (
        '<font face="sans-serif" size="36">{\\an7}'
        '<font size="18"><font color="#00ff00">そこうしゃ</font></font>'
        '<font color="#00ff00">(キュゥべえ)時間遡行者 暁美ほむら｡</font></font>'
    )

    assert clean_caption_text(raw) == "(キュゥべえ)時間遡行者 暁美ほむら｡"


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

