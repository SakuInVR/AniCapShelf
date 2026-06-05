from datetime import datetime

from anicapshelf.parsers import parse_capture_time, parse_recording_name


def test_parse_recording_name_with_episode_and_flag():
    parsed = parse_recording_name(
        "2026年02月27日00時30分00秒-穏やか貴族の休暇のすすめ。　＃８[字].m2ts"
    )

    assert parsed.start_at == datetime(2026, 2, 27, 0, 30, 0)
    assert parsed.title == "穏やか貴族の休暇のすすめ。　＃８[字]"
    assert parsed.episode_token == "＃８"
    assert parsed.flags == "字"


def test_parse_recording_name_without_expected_pattern():
    parsed = parse_recording_name("番組名だけ.ts")

    assert parsed.start_at is None
    assert parsed.title is None
    assert parsed.episode_token is None
    assert parsed.flags == ""


def test_parse_capture_time():
    assert parse_capture_time("Capture_20260115-015919.jpg") == datetime(
        2026, 1, 15, 1, 59, 19
    )


def test_parse_capture_time_with_suffix():
    assert parse_capture_time("Capture_20260122-030834-1.jpg") == datetime(
        2026, 1, 22, 3, 8, 34
    )

