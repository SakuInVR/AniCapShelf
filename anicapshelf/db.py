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
    method TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (capture_id, recording_id, method),
    FOREIGN KEY (capture_id) REFERENCES captures(id) ON DELETE CASCADE,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_matches_recording_id ON capture_recording_matches(recording_id);

CREATE TABLE IF NOT EXISTS subtitles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL,
    start_seconds REAL NOT NULL,
    end_seconds REAL,
    text TEXT NOT NULL,
    raw_text TEXT,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subtitles_recording_time ON subtitles(recording_id, start_seconds);

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
    conn.commit()


def ensure_column(
    conn: sqlite3.Connection, table_name: str, column_name: str, column_type: str
) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
