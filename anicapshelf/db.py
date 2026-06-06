from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS recordings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    extension TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    start_at TEXT,
    end_at TEXT,
    duration_seconds REAL,
    title TEXT,
    normalized_title TEXT,
    series_title TEXT,
    episode_token TEXT,
    episode_number INTEGER,
    subtitle TEXT,
    flags TEXT,
    has_arib_caption INTEGER,
    scanned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_recordings_start_end ON recordings(start_at, end_at);
CREATE INDEX IF NOT EXISTS idx_recordings_title ON recordings(title);

CREATE TABLE IF NOT EXISTS recording_streams (
    recording_id INTEGER NOT NULL,
    stream_index INTEGER NOT NULL,
    codec_type TEXT,
    codec_name TEXT,
    raw_json TEXT NOT NULL,
    probed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (recording_id, stream_index),
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_recording_streams_type
ON recording_streams(recording_id, codec_type, codec_name);

CREATE TABLE IF NOT EXISTS captures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    extension TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    captured_at TEXT,
    modified_at TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    source_hint TEXT,
    scanned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_captures_captured_at ON captures(captured_at);

CREATE TABLE IF NOT EXISTS capture_recording_matches (
    capture_id INTEGER NOT NULL,
    recording_id INTEGER NOT NULL,
    source_time_seconds REAL,
    confidence REAL NOT NULL,
    confidence_reason TEXT,
    is_best INTEGER NOT NULL DEFAULT 0,
    method TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (capture_id, recording_id, method),
    FOREIGN KEY (capture_id) REFERENCES captures(id) ON DELETE CASCADE,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_matches_recording_id ON capture_recording_matches(recording_id);

CREATE TABLE IF NOT EXISTS capture_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_id INTEGER NOT NULL,
    source_app TEXT NOT NULL,
    external_program_id TEXT,
    external_video_id TEXT,
    recording_file_path TEXT,
    playback_position_seconds REAL,
    source_url TEXT,
    tags_json TEXT,
    note TEXT,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (capture_id) REFERENCES captures(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_capture_annotations_capture_id
ON capture_annotations(capture_id);

CREATE INDEX IF NOT EXISTS idx_capture_annotations_source
ON capture_annotations(source_app, external_program_id);

CREATE TABLE IF NOT EXISTS subtitles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL,
    cue_index INTEGER,
    start_seconds REAL NOT NULL,
    end_seconds REAL,
    text TEXT NOT NULL,
    raw_text TEXT,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subtitles_recording_time ON subtitles(recording_id, start_seconds);
CREATE INDEX IF NOT EXISTS idx_subtitles_recording_cue ON subtitles(recording_id, cue_index);

CREATE TABLE IF NOT EXISTS capture_subtitle_links (
    capture_id INTEGER NOT NULL,
    subtitle_id INTEGER NOT NULL,
    offset_seconds REAL NOT NULL,
    method TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (capture_id, subtitle_id, method),
    FOREIGN KEY (capture_id) REFERENCES captures(id) ON DELETE CASCADE,
    FOREIGN KEY (subtitle_id) REFERENCES subtitles(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_capture_subtitle_links_capture_id
ON capture_subtitle_links(capture_id);

CREATE TABLE IF NOT EXISTS capture_ocr_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_id INTEGER NOT NULL,
    engine TEXT NOT NULL,
    text TEXT NOT NULL,
    raw_text TEXT,
    language TEXT,
    confidence REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (capture_id) REFERENCES captures(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_capture_ocr_results_capture_id
ON capture_ocr_results(capture_id);

CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collection_items (
    collection_id INTEGER NOT NULL,
    capture_id INTEGER NOT NULL,
    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (collection_id, capture_id),
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
    FOREIGN KEY (capture_id) REFERENCES captures(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_collection_items_capture_id
ON collection_items(capture_id);

CREATE TABLE IF NOT EXISTS sharex_history (
    id INTEGER PRIMARY KEY,
    file_path TEXT,
    date_time TEXT,
    type TEXT,
    host TEXT,
    url TEXT,
    thumbnail_url TEXT,
    tags TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
    entity_type,
    entity_id UNINDEXED,
    capture_id UNINDEXED,
    recording_id UNINDEXED,
    title,
    body,
    tags,
    source,
    tokenize = 'unicode61'
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    ensure_column(conn, "recordings", "normalized_title", "TEXT")
    ensure_column(conn, "recordings", "series_title", "TEXT")
    ensure_column(conn, "recordings", "episode_number", "INTEGER")
    ensure_column(conn, "recordings", "subtitle", "TEXT")
    ensure_column(conn, "capture_recording_matches", "is_best", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "capture_recording_matches", "confidence_reason", "TEXT")
    ensure_column(conn, "capture_annotations", "tags_json", "TEXT")
    ensure_column(conn, "capture_annotations", "note", "TEXT")
    ensure_column(conn, "subtitles", "cue_index", "INTEGER")
    backfill_subtitle_cue_indexes(conn)
    conn.commit()


def ensure_column(
    conn: sqlite3.Connection, table_name: str, column_name: str, column_type: str
) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}
    if column_name not in columns:
        try:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc):
                raise


def backfill_subtitle_cue_indexes(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id
        FROM subtitles
        WHERE cue_index IS NULL
        ORDER BY recording_id, start_seconds, id
        """
    ).fetchall()
    if not rows:
        return
    ranked = conn.execute(
        """
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY recording_id
                ORDER BY start_seconds, id
            ) AS cue_index
        FROM subtitles
        """
    ).fetchall()
    conn.executemany(
        "UPDATE subtitles SET cue_index = ? WHERE id = ? AND cue_index IS NULL",
        [(row["cue_index"], row["id"]) for row in ranked],
    )
