from __future__ import annotations

import json
import mimetypes
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class AnnotationResult:
    capture_id: int
    annotation_id: int
    image_path: Path


@dataclass(frozen=True)
class ExistingCaptureAnnotationResult:
    capture_id: int
    annotation_id: int
    subtitle_links: int


def save_annotated_capture(
    conn: sqlite3.Connection,
    *,
    image_bytes: bytes,
    original_filename: str,
    metadata: dict,
    output_root: str | Path,
    tags: list[str] | None = None,
    note: str | None = None,
) -> AnnotationResult:
    if not image_bytes:
        raise ValueError("image is empty")
    output_root_path = Path(output_root)
    output_root_path.mkdir(parents=True, exist_ok=True)
    image_path = build_capture_path(output_root_path, original_filename, metadata)
    image_path.write_bytes(image_bytes)

    stat = image_path.stat()
    captured_at_text = normalize_captured_at(metadata.get("captured_at"))
    if captured_at_text is None:
        captured_at_text = iso(datetime.fromtimestamp(stat.st_mtime))
    modified_at_text = iso(datetime.fromtimestamp(stat.st_mtime))
    width, height = open_image_size(image_path)
    source_hint = str(metadata.get("source_app") or "annotated")

    cursor = conn.execute(
        """
        INSERT INTO captures (
            path, filename, extension, size_bytes, captured_at, modified_at,
            width, height, source_hint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            filename=excluded.filename,
            extension=excluded.extension,
            size_bytes=excluded.size_bytes,
            captured_at=excluded.captured_at,
            modified_at=excluded.modified_at,
            width=excluded.width,
            height=excluded.height,
            source_hint=excluded.source_hint,
            scanned_at=CURRENT_TIMESTAMP
        RETURNING id
        """,
        (
            str(image_path),
            image_path.name,
            image_path.suffix.lower(),
            stat.st_size,
            captured_at_text,
            modified_at_text,
            width,
            height,
            source_hint,
        ),
    )
    capture_id = int(cursor.fetchone()["id"])
    normalized_tags = normalize_tags(tags or [])
    tags_json = json.dumps(normalized_tags, ensure_ascii=False)
    metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    annotation_cursor = conn.execute(
        """
        INSERT INTO capture_annotations (
            capture_id, source_app, external_program_id, external_video_id,
            recording_file_path, playback_position_seconds, source_url,
            tags_json, note, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            capture_id,
            str(metadata.get("source_app") or "unknown"),
            optional_text(metadata.get("recorded_program_id")),
            optional_text(metadata.get("recorded_video_id")),
            optional_text(metadata.get("recording_file_path")),
            optional_float(metadata.get("playback_position_seconds")),
            optional_text(metadata.get("konomitv_url") or metadata.get("source_url")),
            tags_json,
            note,
            metadata_json,
        ),
    )
    attach_nearby_subtitles(conn, capture_id=capture_id, metadata=metadata)
    conn.commit()
    return AnnotationResult(
        capture_id=capture_id,
        annotation_id=int(annotation_cursor.lastrowid),
        image_path=image_path,
    )


def annotate_existing_capture(
    conn: sqlite3.Connection,
    *,
    capture_id: int,
    metadata: dict,
    tags: list[str] | None = None,
    note: str | None = None,
    source_app: str = "AniCapShelfBackfill",
) -> ExistingCaptureAnnotationResult:
    capture = conn.execute("SELECT id FROM captures WHERE id = ?", (capture_id,)).fetchone()
    if capture is None:
        raise ValueError(f"capture not found: {capture_id}")
    metadata = dict(metadata)
    metadata.setdefault("source_app", source_app)
    normalized_tags = normalize_tags(tags or [])
    tags_json = json.dumps(normalized_tags, ensure_ascii=False)
    metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    annotation_cursor = conn.execute(
        """
        INSERT INTO capture_annotations (
            capture_id, source_app, external_program_id, external_video_id,
            recording_file_path, playback_position_seconds, source_url,
            tags_json, note, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            capture_id,
            str(metadata.get("source_app") or source_app),
            optional_text(metadata.get("recorded_program_id")),
            optional_text(metadata.get("recorded_video_id")),
            optional_text(metadata.get("recording_file_path")),
            optional_float(metadata.get("playback_position_seconds")),
            optional_text(metadata.get("konomitv_url") or metadata.get("source_url")),
            tags_json,
            note,
            metadata_json,
        ),
    )
    linked = attach_nearby_subtitles(conn, capture_id=capture_id, metadata=metadata)
    conn.commit()
    return ExistingCaptureAnnotationResult(
        capture_id=capture_id,
        annotation_id=int(annotation_cursor.lastrowid),
        subtitle_links=linked,
    )


def build_capture_path(output_root: Path, original_filename: str, metadata: dict) -> Path:
    ext = Path(original_filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        guessed_ext = mimetypes.guess_extension(str(metadata.get("content_type") or ""))
        ext = guessed_ext if guessed_ext in ALLOWED_IMAGE_EXTS else ".jpg"
    timestamp = filename_timestamp(metadata.get("captured_at"))
    source_app = safe_filename(str(metadata.get("source_app") or "capture"))
    program_id = safe_filename(str(metadata.get("recorded_program_id") or "unknown"))
    name = f"{timestamp}-{source_app}-{program_id}-{uuid4().hex[:8]}{ext}"
    return output_root / name


def filename_timestamp(value: object) -> str:
    dt = parse_datetime(value)
    if dt is None:
        dt = datetime.now(timezone.utc).astimezone()
    return dt.strftime("%Y%m%d-%H%M%S")


def normalize_captured_at(value: object) -> str | None:
    dt = parse_datetime(value)
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds")


def parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe.strip("._") or "unknown"


def normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        value = str(tag).strip()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def attach_nearby_subtitles(
    conn: sqlite3.Connection,
    *,
    capture_id: int,
    metadata: dict,
    window_seconds: float = 10.0,
) -> int:
    recording_file_path = optional_text(metadata.get("recording_file_path"))
    playback_position = optional_float(metadata.get("playback_position_seconds"))
    if recording_file_path is None or playback_position is None:
        return 0
    recording = conn.execute(
        "SELECT id FROM recordings WHERE path = ?",
        (recording_file_path,),
    ).fetchone()
    if recording is None:
        return 0
    rows = conn.execute(
        """
        SELECT id, start_seconds
        FROM subtitles
        WHERE recording_id = ?
          AND start_seconds BETWEEN ? AND ?
        ORDER BY ABS(start_seconds - ?), start_seconds
        """,
        (
            recording["id"],
            playback_position - window_seconds,
            playback_position + window_seconds,
            playback_position,
        ),
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO capture_subtitle_links (
                capture_id, subtitle_id, offset_seconds, method
            ) VALUES (?, ?, ?, 'annotation-time-window')
            """,
            (
                capture_id,
                row["id"],
                float(row["start_seconds"]) - playback_position,
            ),
        )
    return len(rows)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


def open_image_size(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None, None
    try:
        with Image.open(path) as img:
            return img.width, img.height
    except Exception:
        return None, None
