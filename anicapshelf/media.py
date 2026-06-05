from __future__ import annotations

import json
import re
import shutil
import subprocess
from html import unescape
from pathlib import Path


def ffprobe_path() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise RuntimeError("ffprobe was not found on PATH")
    return path


def ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg was not found on PATH")
    return path


def probe_streams(path: str | Path) -> list[dict]:
    proc = subprocess.run(
        [
            ffprobe_path(),
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type,codec_name",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return []
    try:
        return json.loads(proc.stdout).get("streams", [])
    except json.JSONDecodeError:
        return []


def has_arib_caption(path: str | Path) -> bool:
    return any(stream.get("codec_name") == "arib_caption" for stream in probe_streams(path))


def extract_srt(path: str | Path, seconds: int | None = None, timeout: int = 180) -> str:
    cmd = [ffmpeg_path(), "-nostdin", "-hide_banner", "-loglevel", "warning"]
    if seconds:
        cmd += ["-t", str(seconds)]
    cmd += ["-i", str(path), "-map", "0:s:0", "-f", "srt", "-"]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        stdout, _ = proc.communicate()
        raise TimeoutError(f"ffmpeg subtitle extraction timed out after {timeout}s") from exc
    return stdout


def extract_srt_preview(
    path: str | Path,
    *,
    seconds: int | None = None,
    max_cues: int = 20,
    timeout: int = 60,
) -> str:
    cmd = [ffmpeg_path(), "-nostdin", "-hide_banner", "-loglevel", "error"]
    if seconds:
        cmd += ["-t", str(seconds)]
    cmd += ["-i", str(path), "-map", "0:s:0", "-f", "srt", "-"]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    lines: list[str] = []
    cue_count = 0
    started = False
    import time

    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if line == "" and proc.poll() is not None:
                break
            if line == "":
                time.sleep(0.05)
                continue
            lines.append(line)
            stripped = line.strip()
            if stripped.isdigit():
                started = True
            elif started and "-->" in stripped:
                cue_count += 1
                if cue_count >= max_cues:
                    break
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
    if cue_count == 0 and time.monotonic() >= deadline:
        raise TimeoutError(f"ffmpeg subtitle preview timed out after {timeout}s")
    return "".join(lines)


SRT_BLOCK_RE = re.compile(
    r"(?ms)^\s*\d+\s*\n"
    r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<end>\d{2,}:\d{2}:\d{2},\d{3})\s*\n"
    r"(?P<text>.*?)(?=\n\s*\d+\s*\n|\Z)"
)

TAG_RE = re.compile(r"<[^>]+>|\{\\[^}]+\}")


def parse_srt_seconds(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def clean_caption_text(raw: str) -> str:
    text = TAG_RE.sub("", raw)
    text = unescape(text)
    text = text.replace("➡", "")
    lines = [line.strip() for line in text.splitlines()]
    return " ".join(line for line in lines if line).strip()


def parse_srt(raw_srt: str) -> list[dict]:
    rows = []
    for match in SRT_BLOCK_RE.finditer(raw_srt):
        raw_text = match.group("text").strip()
        text = clean_caption_text(raw_text)
        if not text:
            continue
        start = parse_srt_seconds(match.group("start"))
        end = parse_srt_seconds(match.group("end"))
        # Some ARIB conversions produce bogus huge end timestamps. Keep the text searchable
        # while avoiding bad range joins.
        if end - start > 600:
            end = None
        rows.append({"start": start, "end": end, "text": text, "raw_text": raw_text})
    return rows
