from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import unicodedata


RECORDING_RE = re.compile(
    r"^(?P<year>\d{4})年(?P<month>\d{2})月(?P<day>\d{2})日"
    r"(?P<hour>\d{2})時(?P<minute>\d{2})分(?P<second>\d{2})秒-"
    r"(?P<title>.+)\.(?P<ext>m2ts|ts)$",
    re.IGNORECASE,
)

CAPTURE_RE = re.compile(
    r"^Capture_(?P<date>\d{8})-(?P<time>\d{6})(?:-\d+)?\.(?P<ext>jpe?g|png)$",
    re.IGNORECASE,
)

EPISODE_RE = re.compile(
    r"(第\s*[０-９0-9一二三四五六七八九十百]+\s*(?:話|回|席|章|輪|羽)|"
    r"[＃#]\s*[０-９0-9]+|"
    r"Episodes?\.?\s*[０-９0-9]+|"
    r"Lesson\.?\s*[０-９0-9]+)",
    re.IGNORECASE,
)

FLAG_RE = re.compile(r"\[(字|解|新|終|再|デ)\]")
BRACKET_FLAG_RE = re.compile(r"\[(?:字|解|新|終|再|デ)\]")
PREFIX_RE = re.compile(r"^(?:アニメA?・|アニメ\s+|[＜<][^＞>]+[＞>])")


@dataclass(frozen=True)
class RecordingName:
    start_at: datetime | None
    title: str | None
    normalized_title: str | None
    series_title: str | None
    episode_token: str | None
    episode_number: int | None
    subtitle: str | None
    flags: str


def parse_recording_name(path: str | Path) -> RecordingName:
    name = Path(path).name
    match = RECORDING_RE.match(name)
    if not match:
        return RecordingName(None, None, None, None, None, None, None, "")

    start_at = datetime(
        int(match.group("year")),
        int(match.group("month")),
        int(match.group("day")),
        int(match.group("hour")),
        int(match.group("minute")),
        int(match.group("second")),
    )
    title = match.group("title")
    episode = EPISODE_RE.search(title)
    flags = ",".join(dict.fromkeys(FLAG_RE.findall(title)))
    normalized = normalize_title(title)
    episode_token = episode.group(0) if episode else None
    episode_number = parse_episode_number(episode_token)
    series_title, subtitle = split_series_and_subtitle(normalized, episode_token)
    return RecordingName(
        start_at,
        title,
        normalized,
        series_title,
        episode_token,
        episode_number,
        subtitle,
        flags,
    )


def parse_capture_time(path: str | Path) -> datetime | None:
    match = CAPTURE_RE.match(Path(path).name)
    if not match:
        return None
    return datetime.strptime(match.group("date") + match.group("time"), "%Y%m%d%H%M%S")


def normalize_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title)
    normalized = normalized.replace("　", " ")
    normalized = BRACKET_FLAG_RE.sub("", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = PREFIX_RE.sub("", normalized).strip()
    normalized = re.sub(r"^(?:[・:：\s]+)", "", normalized)
    return normalized


KANJI_NUMBERS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "百": 100,
}


def parse_episode_number(token: str | None) -> int | None:
    if not token:
        return None
    normalized = unicodedata.normalize("NFKC", token)
    digit = re.search(r"\d+", normalized)
    if digit:
        return int(digit.group(0))
    match = re.search(r"[零〇一二三四五六七八九十百]+", normalized)
    if not match:
        return None
    return kanji_number_to_int(match.group(0))


def kanji_number_to_int(value: str) -> int | None:
    if value == "十":
        return 10
    if "百" in value:
        left, _, right = value.partition("百")
        hundreds = kanji_number_to_int(left) if left else 1
        rest = kanji_number_to_int(right) if right else 0
        return (hundreds or 0) * 100 + (rest or 0)
    if "十" in value:
        left, _, right = value.partition("十")
        tens = KANJI_NUMBERS.get(left, 1) if left else 1
        ones = KANJI_NUMBERS.get(right, 0) if right else 0
        return tens * 10 + ones
    total = 0
    for char in value:
        if char not in KANJI_NUMBERS:
            return None
        total = total * 10 + KANJI_NUMBERS[char]
    return total


def split_series_and_subtitle(
    normalized_title: str, episode_token: str | None
) -> tuple[str | None, str | None]:
    title = normalized_title.strip()
    if not title:
        return None, None
    if episode_token:
        token = unicodedata.normalize("NFKC", episode_token)
        match = re.search(re.escape(token), title)
        if match:
            series = title[: match.start()].strip(" -:：・")
            subtitle = title[match.end() :].strip(" -:：・")
            subtitle = subtitle.strip("「」『』")
            return series or title, subtitle or None
    quoted = re.search(r"[「『](?P<subtitle>.+?)[」』]\s*$", title)
    if quoted:
        series = title[: quoted.start()].strip(" -:：・")
        return series or title, quoted.group("subtitle")
    return title, None
