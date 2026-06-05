from datetime import datetime

from anicapshelf.parsers import (
    normalize_title,
    parse_capture_time,
    parse_episode_number,
    parse_recording_name,
)


def test_parse_recording_name_with_episode_and_flag():
    parsed = parse_recording_name(
        "2026年02月27日00時30分00秒-穏やか貴族の休暇のすすめ。　＃８[字].m2ts"
    )

    assert parsed.start_at == datetime(2026, 2, 27, 0, 30, 0)
    assert parsed.title == "穏やか貴族の休暇のすすめ。　＃８[字]"
    assert parsed.normalized_title == "穏やか貴族の休暇のすすめ。 #8"
    assert parsed.series_title == "穏やか貴族の休暇のすすめ。"
    assert parsed.episode_token == "＃８"
    assert parsed.episode_number == 8
    assert parsed.subtitle is None
    assert parsed.flags == "字"


def test_parse_recording_name_without_expected_pattern():
    parsed = parse_recording_name("番組名だけ.ts")

    assert parsed.start_at is None
    assert parsed.title is None
    assert parsed.normalized_title is None
    assert parsed.series_title is None
    assert parsed.episode_token is None
    assert parsed.episode_number is None
    assert parsed.subtitle is None
    assert parsed.flags == ""


def test_parse_capture_time():
    assert parse_capture_time("Capture_20260115-015919.jpg") == datetime(
        2026, 1, 15, 1, 59, 19
    )


def test_parse_capture_time_with_suffix():
    assert parse_capture_time("Capture_20260122-030834-1.jpg") == datetime(
        2026, 1, 22, 3, 8, 34
    )


def test_parse_recording_name_splits_quoted_subtitle():
    parsed = parse_recording_name(
        "2026年01月10日02時00分00秒-機甲創世記モスピーダ　＃１５「仲間割れのバラード」.m2ts"
    )

    assert parsed.normalized_title == "機甲創世記モスピーダ #15「仲間割れのバラード」"
    assert parsed.series_title == "機甲創世記モスピーダ"
    assert parsed.episode_number == 15
    assert parsed.subtitle == "仲間割れのバラード"


def test_normalize_title_removes_common_prefix_and_flags():
    assert normalize_title("[新]アニメ　葬送のフリーレン　第３４話　討伐要請[字]") == (
        "葬送のフリーレン 第34話 討伐要請"
    )


def test_parse_episode_number_from_kanji():
    assert parse_episode_number("第十七話") == 17
