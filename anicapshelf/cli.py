from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from .api import run_server
from .config import load_config
from .db import connect, init_db
from .media import (
    extract_srt,
    extract_srt_preview,
    has_arib_caption,
    parse_srt,
    probe_streams,
    stream_to_json,
)
from .parsers import parse_capture_time, parse_recording_name

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
RECORDING_EXTS = {".ts", ".m2ts"}


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


def iter_files(root: Path, exts: set[str]):
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() in exts:
                yield path


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


def cmd_scan_records(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    init_db(conn)
    config = load_config(args.config)
    records_root = args.records_root or config.records_root
    if not records_root:
        raise SystemExit("--records-root または設定ファイルの roots.records が必要です")
    root = Path(records_root)
    count = 0
    created = 0
    updated = 0
    skipped = 0
    caption_count = 0
    for path in iter_files(root, RECORDING_EXTS):
        stat = path.stat()
        parsed = parse_recording_name(path)
        start_at = parsed.start_at
        end_at = datetime.fromtimestamp(stat.st_mtime)
        duration = (end_at - start_at).total_seconds() if start_at else None
        end_at_text = iso(end_at)
        existing = conn.execute(
            "SELECT size_bytes, end_at, has_arib_caption FROM recordings WHERE path = ?",
            (str(path),),
        ).fetchone()
        if existing is None:
            created += 1
        elif existing["size_bytes"] == stat.st_size and existing["end_at"] == end_at_text:
            skipped += 1
        else:
            updated += 1
        has_caption = existing["has_arib_caption"] if existing is not None else None
        if args.probe_subtitles:
            has_caption = 1 if has_arib_caption(path, args.probe_timeout) else 0
            caption_count += int(bool(has_caption))
        conn.execute(
            """
            INSERT INTO recordings (
                path, filename, extension, size_bytes, start_at, end_at,
                duration_seconds, title, normalized_title, series_title,
                episode_token, episode_number, subtitle, flags, has_arib_caption
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                filename=excluded.filename,
                extension=excluded.extension,
                size_bytes=excluded.size_bytes,
                start_at=excluded.start_at,
                end_at=excluded.end_at,
                duration_seconds=excluded.duration_seconds,
                title=excluded.title,
                normalized_title=excluded.normalized_title,
                series_title=excluded.series_title,
                episode_token=excluded.episode_token,
                episode_number=excluded.episode_number,
                subtitle=excluded.subtitle,
                flags=excluded.flags,
                has_arib_caption=excluded.has_arib_caption,
                scanned_at=CURRENT_TIMESTAMP
            """,
            (
                str(path),
                path.name,
                path.suffix.lower(),
                stat.st_size,
                iso(start_at),
                end_at_text,
                duration,
                parsed.title,
                parsed.normalized_title,
                parsed.series_title,
                parsed.episode_token,
                parsed.episode_number,
                parsed.subtitle,
                parsed.flags,
                has_caption,
            ),
        )
        count += 1
    conn.commit()
    print(f"recordings indexed: {count}")
    print(f"created: {created}")
    print(f"updated: {updated}")
    print(f"skipped: {skipped}")
    if args.probe_subtitles:
        print(f"recordings with arib captions: {caption_count}")


def cmd_scan_captures(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    init_db(conn)
    config = load_config(args.config)
    captures_root = args.captures_root or config.captures_root
    if not captures_root:
        raise SystemExit("--captures-root または設定ファイルの roots.captures が必要です")
    root = Path(captures_root)
    count = 0
    created = 0
    updated = 0
    skipped = 0
    for path in iter_files(root, IMAGE_EXTS):
        stat = path.stat()
        captured_at = parse_capture_time(path) or datetime.fromtimestamp(stat.st_mtime)
        modified_at_text = iso(datetime.fromtimestamp(stat.st_mtime))
        existing = conn.execute(
            "SELECT size_bytes, modified_at FROM captures WHERE path = ?", (str(path),)
        ).fetchone()
        if existing is None:
            created += 1
        elif existing["size_bytes"] == stat.st_size and existing["modified_at"] == modified_at_text:
            skipped += 1
        else:
            updated += 1
        width, height = open_image_size(path)
        source_hint = "sharex" if "ShareX" in path.parts else "capture"
        conn.execute(
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
            """,
            (
                str(path),
                path.name,
                path.suffix.lower(),
                stat.st_size,
                iso(captured_at),
                modified_at_text,
                width,
                height,
                source_hint,
            ),
        )
        count += 1
    conn.commit()
    print(f"captures indexed: {count}")
    print(f"created: {created}")
    print(f"updated: {updated}")
    print(f"skipped: {skipped}")


def cmd_match(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    init_db(conn)
    conn.execute("DELETE FROM capture_recording_matches WHERE method='time-window'")
    captures = conn.execute(
        "SELECT id, captured_at FROM captures WHERE captured_at IS NOT NULL"
    ).fetchall()
    recordings = conn.execute(
        "SELECT id, start_at, end_at FROM recordings WHERE start_at IS NOT NULL AND end_at IS NOT NULL"
    ).fetchall()
    matched = 0
    candidates = 0
    window_seconds = args.window_minutes * 60
    for capture in captures:
        captured_at = datetime.fromisoformat(capture["captured_at"])
        hits = []
        for recording in recordings:
            start_at = datetime.fromisoformat(recording["start_at"])
            end_at = datetime.fromisoformat(recording["end_at"])
            if (start_at.timestamp() - window_seconds) <= captured_at.timestamp() <= (
                end_at.timestamp() + window_seconds
            ):
                hits.append((recording["id"], (captured_at - start_at).total_seconds()))
        if hits:
            matched += 1
            candidates += len(hits)
        scored_hits = []
        for recording_id, source_seconds in hits:
            confidence = 0.9 if source_seconds >= 0 else 0.6
            scored_hits.append((recording_id, source_seconds, confidence))
        best = sorted(scored_hits, key=lambda item: (-item[2], abs(item[1])))[0] if scored_hits else None
        for recording_id, source_seconds, confidence in scored_hits:
            conn.execute(
                """
                INSERT OR REPLACE INTO capture_recording_matches (
                    capture_id, recording_id, source_time_seconds, confidence, is_best, method
                ) VALUES (?, ?, ?, ?, ?, 'time-window')
                """,
                (
                    capture["id"],
                    recording_id,
                    source_seconds,
                    confidence,
                    1 if best and recording_id == best[0] else 0,
                ),
            )
    conn.commit()
    print(f"captures considered: {len(captures)}")
    print(f"captures matched: {matched}")
    print(f"match candidates: {candidates}")


def cmd_probe_subtitles(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    records_root = args.records_root or config.records_root
    if not records_root:
        raise SystemExit("--records-root または設定ファイルの roots.records が必要です")
    root = Path(records_root)
    files = list(iter_files(root, RECORDING_EXTS))[: args.limit]
    count = 0
    for path in files:
        if has_arib_caption(path, args.timeout):
            count += 1
            print(f"caption: {path}")
        elif args.verbose:
            print(f"no caption: {path}")
    print(f"sampled={len(files)} arib_caption={count}")


def cmd_probe_recording_captions(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    init_db(conn)
    query = """
        SELECT id, path
        FROM recordings
        WHERE path IS NOT NULL
        ORDER BY id
    """
    if args.only_unknown:
        query = """
            SELECT id, path
            FROM recordings
            WHERE path IS NOT NULL AND has_arib_caption IS NULL
            ORDER BY id
        """
    rows = conn.execute(query).fetchall()
    if args.limit:
        rows = rows[: args.limit]
    checked = 0
    found = 0
    missing = 0
    for row in rows:
        checked += 1
        has_caption = has_arib_caption(row["path"], args.timeout)
        found += int(has_caption)
        missing += int(not has_caption)
        conn.execute(
            "UPDATE recordings SET has_arib_caption = ? WHERE id = ?",
            (1 if has_caption else 0, row["id"]),
        )
        if args.verbose:
            label = "caption" if has_caption else "no-caption"
            print(f"{label}: {row['path']}")
        if checked % args.commit_every == 0:
            conn.commit()
    conn.commit()
    print(f"recordings checked: {checked}")
    print(f"arib_caption: {found}")
    print(f"without_arib_caption: {missing}")


def cmd_probe_recording_streams(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    init_db(conn)
    rows = conn.execute(
        """
        SELECT id, path
        FROM recordings
        WHERE path IS NOT NULL
        ORDER BY id
        """
    ).fetchall()
    if args.limit:
        rows = rows[: args.limit]
    checked = 0
    streams_saved = 0
    no_streams = 0
    for row in rows:
        checked += 1
        streams = probe_streams(row["path"], args.timeout)
        if not streams:
            no_streams += 1
        conn.execute("DELETE FROM recording_streams WHERE recording_id = ?", (row["id"],))
        for stream in streams:
            stream_index = stream.get("index")
            if stream_index is None:
                continue
            conn.execute(
                """
                INSERT INTO recording_streams (
                    recording_id, stream_index, codec_type, codec_name, raw_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    stream_index,
                    stream.get("codec_type"),
                    stream.get("codec_name"),
                    stream_to_json(stream),
                ),
            )
            streams_saved += 1
        if args.verbose:
            print(f"{len(streams)} streams: {row['path']}")
        if checked % args.commit_every == 0:
            conn.commit()
    conn.commit()
    print(f"recordings checked: {checked}")
    print(f"streams saved: {streams_saved}")
    print(f"recordings without streams: {no_streams}")


def cmd_extract_subtitles(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    init_db(conn)
    row = conn.execute(
        "SELECT id, path FROM recordings WHERE id = ?", (args.recording_id,)
    ).fetchone()
    if row is None:
        raise SystemExit(f"recording not found: {args.recording_id}")
    try:
        if args.max_cues:
            raw = extract_srt_preview(
                row["path"], seconds=args.seconds, max_cues=args.max_cues, timeout=args.timeout
            )
        else:
            raw = extract_srt(row["path"], args.seconds, args.timeout)
    except TimeoutError as exc:
        raise SystemExit(str(exc)) from exc
    subtitles = parse_srt(raw)
    conn.execute("DELETE FROM subtitles WHERE recording_id = ?", (row["id"],))
    conn.executemany(
        """
        INSERT INTO subtitles (recording_id, start_seconds, end_seconds, text, raw_text, source)
        VALUES (?, ?, ?, ?, ?, 'arib_caption')
        """,
        [
            (row["id"], item["start"], item["end"], item["text"], item["raw_text"])
            for item in subtitles
        ],
    )
    conn.commit()
    print(f"subtitles extracted: {len(subtitles)}")
    for item in subtitles[: args.preview]:
        print(f"{item['start']:.3f}: {item['text']}")


def cmd_import_sharex(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    history_db = args.history_db or config.sharex_history_db
    if not history_db:
        raise SystemExit("--history-db または設定ファイルの sharex.history_db が必要です")
    src = sqlite3.connect(history_db)
    src.row_factory = sqlite3.Row
    dst = connect(args.db)
    init_db(dst)
    rows = src.execute(
        "SELECT Id, FilePath, DateTime, Type, Host, URL, ThumbnailURL, Tags FROM History"
    ).fetchall()
    for row in rows:
        dst.execute(
            """
            INSERT OR REPLACE INTO sharex_history (
                id, file_path, date_time, type, host, url, thumbnail_url, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["Id"],
                row["FilePath"],
                row["DateTime"],
                row["Type"],
                row["Host"],
                row["URL"],
                row["ThumbnailURL"],
                row["Tags"],
            ),
        )
    dst.commit()
    print(f"sharex history imported: {len(rows)}")


def cmd_report(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    init_db(conn)
    queries = {
        "recordings": "SELECT COUNT(*) FROM recordings",
        "recordings_with_title": "SELECT COUNT(*) FROM recordings WHERE title IS NOT NULL",
        "recordings_with_series": "SELECT COUNT(*) FROM recordings WHERE series_title IS NOT NULL",
        "recordings_with_episode": "SELECT COUNT(*) FROM recordings WHERE episode_token IS NOT NULL",
        "recordings_with_arib_caption": "SELECT COUNT(*) FROM recordings WHERE has_arib_caption = 1",
        "recording_streams": "SELECT COUNT(*) FROM recording_streams",
        "captures": "SELECT COUNT(*) FROM captures",
        "captures_matched": "SELECT COUNT(DISTINCT capture_id) FROM capture_recording_matches",
        "match_candidates": "SELECT COUNT(*) FROM capture_recording_matches",
        "capture_annotations": "SELECT COUNT(*) FROM capture_annotations",
        "capture_subtitle_links": "SELECT COUNT(*) FROM capture_subtitle_links",
        "subtitles": "SELECT COUNT(*) FROM subtitles",
        "sharex_history": "SELECT COUNT(*) FROM sharex_history",
    }
    for label, query in queries.items():
        print(f"{label}: {conn.execute(query).fetchone()[0]}")


def cmd_review_unmatched(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    init_db(conn)
    rows = conn.execute(
        """
        SELECT c.id, c.captured_at, c.filename, c.source_hint, c.path
        FROM captures c
        LEFT JOIN capture_recording_matches m ON m.capture_id = c.id
        WHERE m.capture_id IS NULL
        ORDER BY c.captured_at DESC, c.id DESC
        LIMIT ?
        """,
        (args.limit,),
    ).fetchall()
    if not rows:
        print("未分類キャプチャはありません")
        return
    for row in rows:
        print(
            "\t".join(
                [
                    str(row["id"]),
                    row["captured_at"] or "",
                    row["source_hint"] or "",
                    row["filename"],
                    row["path"],
                ]
            )
        )


def cmd_review_ambiguous(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    init_db(conn)
    rows = conn.execute(
        """
        SELECT
            c.id AS capture_id,
            c.captured_at,
            c.filename AS capture_filename,
            c.source_hint,
            COUNT(m.recording_id) AS candidate_count
        FROM captures c
        JOIN capture_recording_matches m ON m.capture_id = c.id
        GROUP BY c.id
        HAVING COUNT(m.recording_id) > 1
        ORDER BY c.captured_at DESC, c.id DESC
        LIMIT ?
        """,
        (args.limit,),
    ).fetchall()
    if not rows:
        print("曖昧なマッチ候補はありません")
        return
    for row in rows:
        print(
            "\t".join(
                [
                    str(row["capture_id"]),
                    row["captured_at"] or "",
                    row["source_hint"] or "",
                    str(row["candidate_count"]),
                    row["capture_filename"],
                ]
            )
        )
        if args.show_candidates:
            candidates = conn.execute(
                """
                SELECT
                    ROUND(m.source_time_seconds, 1) AS source_time_seconds,
                    m.confidence,
                    m.is_best,
                    r.title,
                    r.path
                FROM capture_recording_matches m
                JOIN recordings r ON r.id = m.recording_id
                WHERE m.capture_id = ?
                ORDER BY m.is_best DESC, m.confidence DESC, ABS(m.source_time_seconds) ASC
                """,
                (row["capture_id"],),
            ).fetchall()
            for candidate in candidates:
                print(
                    "  - "
                    + "\t".join(
                        [
                            "best" if candidate["is_best"] else "candidate",
                            str(candidate["source_time_seconds"]),
                            str(candidate["confidence"]),
                            candidate["title"] or "",
                            candidate["path"],
                        ]
                    )
                )


def fetch_capture_detail(conn: sqlite3.Connection, capture_id: int) -> dict | None:
    capture = conn.execute("SELECT * FROM captures WHERE id = ?", (capture_id,)).fetchone()
    if capture is None:
        return None
    annotations = [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM capture_annotations
            WHERE capture_id = ?
            ORDER BY id DESC
            """,
            (capture_id,),
        ).fetchall()
    ]
    matches = [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                m.recording_id,
                m.source_time_seconds,
                m.confidence,
                m.is_best,
                m.method,
                r.path AS recording_path,
                r.title,
                r.series_title,
                r.episode_number,
                r.subtitle
            FROM capture_recording_matches m
            JOIN recordings r ON r.id = m.recording_id
            WHERE m.capture_id = ?
            ORDER BY m.is_best DESC, m.confidence DESC, ABS(m.source_time_seconds) ASC
            """,
            (capture_id,),
        ).fetchall()
    ]
    subtitles = [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                s.id AS subtitle_id,
                s.recording_id,
                s.start_seconds,
                s.end_seconds,
                s.text,
                s.source,
                l.offset_seconds,
                l.method
            FROM capture_subtitle_links l
            JOIN subtitles s ON s.id = l.subtitle_id
            WHERE l.capture_id = ?
            ORDER BY ABS(l.offset_seconds), s.start_seconds
            """,
            (capture_id,),
        ).fetchall()
    ]
    return {
        "capture": dict(capture),
        "annotations": [decode_annotation_json(row) for row in annotations],
        "source_jump": build_source_jump(annotations),
        "matches": matches,
        "subtitles": subtitles,
    }


def decode_annotation_json(row: dict) -> dict:
    decoded = dict(row)
    decoded["tags"] = json_loads_or_default(decoded.pop("tags_json", None), [])
    decoded["metadata"] = json_loads_or_default(decoded.pop("metadata_json", None), {})
    return decoded


def json_loads_or_default(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def build_source_jump(annotation_rows: list[dict]) -> dict | None:
    for row in annotation_rows:
        playback_position = row.get("playback_position_seconds")
        source_url = row.get("source_url")
        recording_file_path = row.get("recording_file_path")
        if playback_position is None and not source_url and not recording_file_path:
            continue
        seconds = float(playback_position) if playback_position is not None else None
        return {
            "source_app": row.get("source_app"),
            "url": source_url,
            "recording_file_path": recording_file_path,
            "playback_position_seconds": seconds,
            "timecode": format_timecode(seconds),
            "open_hint": build_open_hint(source_url, seconds),
        }
    return None


def format_timecode(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"


def build_open_hint(source_url: str | None, seconds: float | None) -> str | None:
    if source_url and seconds is not None:
        return f"{source_url} を開いて {format_timecode(seconds)} に移動"
    if source_url:
        return f"{source_url} を開く"
    if seconds is not None:
        return f"{format_timecode(seconds)} に移動"
    return None


def cmd_show_capture(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    init_db(conn)
    detail = fetch_capture_detail(conn, args.capture_id)
    conn.close()
    if detail is None:
        raise SystemExit(f"capture not found: {args.capture_id}")
    if args.format == "json":
        print(json.dumps(detail, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print_capture_detail(detail)


def print_capture_detail(detail: dict) -> None:
    capture = detail["capture"]
    print(f"capture_id: {capture['id']}")
    print(f"filename: {capture['filename']}")
    print(f"path: {capture['path']}")
    print(f"captured_at: {capture['captured_at'] or ''}")
    print(f"source_hint: {capture['source_hint'] or ''}")
    if capture["width"] and capture["height"]:
        print(f"size: {capture['width']}x{capture['height']}")
    if detail["source_jump"]:
        source_jump = detail["source_jump"]
        print("source_jump:")
        print(f"  app: {source_jump['source_app'] or ''}")
        print(f"  open_url: {source_jump['url'] or ''}")
        print(f"  timecode: {source_jump['timecode'] or ''}")
        playback_position = source_jump["playback_position_seconds"]
        print(
            "  playback_position_seconds: "
            + (str(playback_position) if playback_position is not None else "")
        )
        print(f"  recording_file_path: {source_jump['recording_file_path'] or ''}")
        print(f"  open_hint: {source_jump['open_hint'] or ''}")
    else:
        print("source_jump: none")
    if detail["annotations"]:
        print("annotations:")
        for annotation in detail["annotations"]:
            print(f"  - annotation_id: {annotation['id']}")
            print(f"    source_app: {annotation['source_app']}")
            print(f"    program_id: {annotation['external_program_id'] or ''}")
            print(f"    video_id: {annotation['external_video_id'] or ''}")
            print(f"    recording_file_path: {annotation['recording_file_path'] or ''}")
            print(f"    playback_position_seconds: {annotation['playback_position_seconds'] or ''}")
            print(f"    source_url: {annotation['source_url'] or ''}")
            print(f"    tags: {', '.join(annotation['tags'])}")
            print(f"    note: {annotation['note'] or ''}")
            metadata = annotation["metadata"]
            title = metadata.get("title") or ""
            episode = metadata.get("episode_number")
            subtitle = metadata.get("subtitle") or ""
            if title or episode or subtitle:
                print(f"    title: {format_title(title, episode, subtitle)}")
    else:
        print("annotations: none")
    if detail["subtitles"]:
        print("subtitles:")
        for subtitle in detail["subtitles"]:
            print(
                "  - "
                + "\t".join(
                    [
                        f"{subtitle['start_seconds']:.3f}",
                        f"offset={subtitle['offset_seconds']:.3f}",
                        subtitle["source"],
                        subtitle["text"],
                    ]
                )
            )
    else:
        print("subtitles: none")
    if detail["matches"]:
        print("matches:")
        for match in detail["matches"]:
            label = "best" if match["is_best"] else "candidate"
            print(
                "  - "
                + "\t".join(
                    [
                        label,
                        f"recording_id={match['recording_id']}",
                        f"source_time_seconds={match['source_time_seconds']}",
                        f"confidence={match['confidence']}",
                        match["title"] or "",
                        match["recording_path"],
                    ]
                )
            )
    else:
        print("matches: none")


def format_title(title: str, episode: object, subtitle: str) -> str:
    parts = [title]
    if episode is not None:
        parts.append(f"第{episode}話")
    if subtitle:
        parts.append(str(subtitle))
    return " ".join(str(part) for part in parts if part)


EXPORT_QUERIES = {
    "recordings": "SELECT * FROM recordings ORDER BY id",
    "captures": "SELECT * FROM captures ORDER BY id",
    "matches": """
        SELECT
            m.capture_id,
            c.path AS capture_path,
            c.captured_at,
            m.recording_id,
            r.path AS recording_path,
            r.title,
            m.source_time_seconds,
            m.confidence,
            m.is_best,
            m.method
        FROM capture_recording_matches m
        JOIN captures c ON c.id = m.capture_id
        JOIN recordings r ON r.id = m.recording_id
        ORDER BY m.capture_id, m.is_best DESC, m.confidence DESC, m.recording_id
    """,
    "annotations": """
        SELECT
            a.id,
            a.capture_id,
            c.path AS capture_path,
            a.source_app,
            a.external_program_id,
            a.external_video_id,
            a.recording_file_path,
            a.playback_position_seconds,
            a.source_url,
            a.tags_json,
            a.note,
            a.metadata_json,
            a.created_at
        FROM capture_annotations a
        JOIN captures c ON c.id = a.capture_id
        ORDER BY a.id
    """,
    "streams": "SELECT * FROM recording_streams ORDER BY recording_id, stream_index",
    "subtitles": "SELECT * FROM subtitles ORDER BY recording_id, start_seconds",
    "subtitle-links": "SELECT * FROM capture_subtitle_links ORDER BY capture_id, subtitle_id",
    "sharex": "SELECT * FROM sharex_history ORDER BY id",
}


def cmd_export(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    init_db(conn)
    query = EXPORT_QUERIES[args.dataset]
    rows = [dict(row) for row in conn.execute(query).fetchall()]
    output_path = Path(args.output) if args.output else None
    if args.format == "jsonl":
        lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
        content = "\n".join(lines)
        if content:
            content += "\n"
    else:
        fieldnames = list(rows[0].keys()) if rows else []
        from io import StringIO

        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
        if fieldnames:
            writer.writeheader()
            writer.writerows(rows)
        content = buffer.getvalue()
    if output_path:
        output_path.write_text(content, encoding="utf-8", newline="")
        print(f"exported {len(rows)} rows: {output_path}")
    else:
        print(content, end="")


def cmd_serve_api(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    capture_output_root = args.capture_output_root or config.captures_root
    if not capture_output_root:
        raise SystemExit("--capture-output-root または設定ファイルの roots.captures が必要です")
    run_server(
        host=args.host,
        port=args.port,
        db_path=args.db,
        capture_output_root=capture_output_root,
        allow_origin=args.allow_origin,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="anicapshelf")
    parser.add_argument("--db", default="anicapshelf.db", help="SQLite database path")
    parser.add_argument(
        "--config",
        default="anicapshelf.toml",
        help="ローカル設定ファイルのパス",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    records = sub.add_parser("scan-records")
    records.add_argument("--records-root")
    records.add_argument("--probe-subtitles", action="store_true")
    records.add_argument("--probe-timeout", type=int, default=30)
    records.set_defaults(func=cmd_scan_records)

    captures = sub.add_parser("scan-captures")
    captures.add_argument("--captures-root")
    captures.set_defaults(func=cmd_scan_captures)

    match = sub.add_parser("match")
    match.add_argument("--window-minutes", type=float, default=2)
    match.set_defaults(func=cmd_match)

    probe = sub.add_parser("probe-subtitles")
    probe.add_argument("--records-root")
    probe.add_argument("--limit", type=int, default=40)
    probe.add_argument("--timeout", type=int, default=30)
    probe.add_argument("--verbose", action="store_true")
    probe.set_defaults(func=cmd_probe_subtitles)

    probe_db = sub.add_parser("probe-recording-captions")
    probe_db.add_argument("--limit", type=int)
    probe_db.add_argument("--timeout", type=int, default=30)
    probe_db.add_argument("--commit-every", type=int, default=25)
    probe_db.add_argument("--only-unknown", action="store_true")
    probe_db.add_argument("--verbose", action="store_true")
    probe_db.set_defaults(func=cmd_probe_recording_captions)

    streams = sub.add_parser("probe-recording-streams")
    streams.add_argument("--limit", type=int)
    streams.add_argument("--timeout", type=int, default=30)
    streams.add_argument("--commit-every", type=int, default=25)
    streams.add_argument("--verbose", action="store_true")
    streams.set_defaults(func=cmd_probe_recording_streams)

    extract = sub.add_parser("extract-subtitles")
    extract.add_argument("--recording-id", type=int, required=True)
    extract.add_argument("--seconds", type=int, default=120)
    extract.add_argument("--timeout", type=int, default=180)
    extract.add_argument("--max-cues", type=int, default=0)
    extract.add_argument("--preview", type=int, default=10)
    extract.set_defaults(func=cmd_extract_subtitles)

    sharex = sub.add_parser("import-sharex")
    sharex.add_argument("--history-db")
    sharex.set_defaults(func=cmd_import_sharex)

    report = sub.add_parser("report")
    report.set_defaults(func=cmd_report)

    unmatched = sub.add_parser("review-unmatched")
    unmatched.add_argument("--limit", type=int, default=50)
    unmatched.set_defaults(func=cmd_review_unmatched)

    ambiguous = sub.add_parser("review-ambiguous")
    ambiguous.add_argument("--limit", type=int, default=50)
    ambiguous.add_argument("--show-candidates", action="store_true")
    ambiguous.set_defaults(func=cmd_review_ambiguous)

    show_capture = sub.add_parser("show-capture")
    show_capture.add_argument("capture_id", type=int)
    show_capture.add_argument("--format", choices=["text", "json"], default="text")
    show_capture.set_defaults(func=cmd_show_capture)

    export = sub.add_parser("export")
    export.add_argument(
        "dataset",
        choices=sorted(EXPORT_QUERIES),
        help="出力するデータセット",
    )
    export.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")
    export.add_argument("--output")
    export.set_defaults(func=cmd_export)

    api = sub.add_parser("serve-api")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8765)
    api.add_argument(
        "--capture-output-root",
        help="アノテーションAPIで受け取った画像の保存先。未指定時は roots.captures を使います。",
    )
    api.add_argument(
        "--allow-origin",
        help="ブラウザ連携を許可するKonomiTVのorigin。例: http://127.0.0.1:7000",
    )
    api.set_defaults(func=cmd_serve_api)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
