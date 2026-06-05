from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


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


@dataclass(frozen=True)
class RecordingName:
    start_at: datetime | None
    title: str | None
    episode_token: str | None
    flags: str


def parse_recording_name(path: str | Path) -> RecordingName:
    name = Path(path).name
    match = RECORDING_RE.match(name)
    if not match:
        return RecordingName(None, None, None, "")

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
    return RecordingName(start_at, title, episode.group(0) if episode else None, flags)


def parse_capture_time(path: str | Path) -> datetime | None:
    match = CAPTURE_RE.match(Path(path).name)
    if not match:
        return None
    return datetime.strptime(match.group("date") + match.group("time"), "%Y%m%d%H%M%S")

