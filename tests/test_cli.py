from __future__ import annotations

from datetime import datetime
from pathlib import Path

from anicapshelf.cli import main


def test_scan_captures_reports_created_and_skipped(tmp_path: Path, capsys):
    captures_root = tmp_path / "captures"
    captures_root.mkdir()
    image_path = captures_root / "Capture_20260115-015919.jpg"
    image_path.write_bytes(b"not a real image, but enough for indexing")
    db_path = tmp_path / "test.db"

    main(
        [
            "--db",
            str(db_path),
            "scan-captures",
            "--captures-root",
            str(captures_root),
        ]
    )
    first = capsys.readouterr().out

    main(
        [
            "--db",
            str(db_path),
            "scan-captures",
            "--captures-root",
            str(captures_root),
        ]
    )
    second = capsys.readouterr().out

    assert "captures indexed: 1" in first
    assert "created: 1" in first
    assert "skipped: 0" in first
    assert "captures indexed: 1" in second
    assert "created: 0" in second
    assert "skipped: 1" in second


def test_scan_records_preserves_existing_caption_probe(tmp_path: Path, capsys):
    records_root = tmp_path / "records"
    records_root.mkdir()
    recording = records_root / "2026年01月10日02時00分00秒-作品　第１話.m2ts"
    recording.write_bytes(b"recording")
    db_path = tmp_path / "test.db"

    main(
        [
            "--db",
            str(db_path),
            "scan-records",
            "--records-root",
            str(records_root),
        ]
    )
    capsys.readouterr()

    import sqlite3

    con = sqlite3.connect(db_path)
    con.execute("UPDATE recordings SET has_arib_caption = 1")
    con.commit()
    con.close()

    main(
        [
            "--db",
            str(db_path),
            "scan-records",
            "--records-root",
            str(records_root),
        ]
    )
    capsys.readouterr()

    con = sqlite3.connect(db_path)
    value = con.execute("SELECT has_arib_caption FROM recordings").fetchone()[0]
    con.close()
    assert value == 1


def test_extract_subtitles_batch_extracts_missing_caption_recordings(
    tmp_path: Path, capsys, monkeypatch
):
    import sqlite3

    db_path = tmp_path / "test.db"
    recording_with_caption = tmp_path / "caption.m2ts"
    recording_without_caption = tmp_path / "no-caption.m2ts"
    recording_with_caption.write_bytes(b"recording")
    recording_without_caption.write_bytes(b"recording")

    from anicapshelf.db import connect, init_db

    conn = connect(db_path)
    init_db(conn)
    conn.execute(
        """
        INSERT INTO recordings (
            path, filename, extension, size_bytes, title, has_arib_caption
        ) VALUES (?, 'caption.m2ts', '.m2ts', 1, '字幕あり', 1)
        """,
        (str(recording_with_caption),),
    )
    conn.execute(
        """
        INSERT INTO recordings (
            path, filename, extension, size_bytes, title, has_arib_caption
        ) VALUES (?, 'no-caption.m2ts', '.m2ts', 1, '字幕なし', 0)
        """,
        (str(recording_without_caption),),
    )
    conn.commit()
    conn.close()

    def fake_extract_srt(path, seconds=None, timeout=180):
        assert Path(path) == recording_with_caption
        return (
            "1\n"
            "00:00:01,000 --> 00:00:03,000\n"
            "ほむらちゃん\n\n"
        )

    monkeypatch.setattr("anicapshelf.cli.extract_srt", fake_extract_srt)

    main(
        [
            "--db",
            str(db_path),
            "extract-subtitles-batch",
            "--only-with-arib",
            "--only-missing",
        ]
    )
    output = capsys.readouterr().out

    con = sqlite3.connect(db_path)
    rows = con.execute(
        """
        SELECT r.title, s.cue_index, s.text
        FROM subtitles s
        JOIN recordings r ON r.id = s.recording_id
        """
    ).fetchall()
    con.close()

    assert "recordings selected: 1" in output
    assert "recordings processed: 1" in output
    assert "subtitles extracted: 1" in output
    assert rows == [("字幕あり", 1, "ほむらちゃん")]


def test_list_subtitles_outputs_recording_subtitle_queue(tmp_path: Path, capsys):
    import json
    import sqlite3

    db_path = tmp_path / "test.db"
    recording_path = tmp_path / "recording.m2ts"
    recording_path.write_bytes(b"recording")

    from anicapshelf.db import connect, init_db

    conn = connect(db_path)
    init_db(conn)
    conn.execute(
        """
        INSERT INTO recordings (
            path, filename, extension, size_bytes, title
        ) VALUES (?, 'recording.m2ts', '.m2ts', 1, '字幕キュー')
        """,
        (str(recording_path),),
    )
    recording_id = conn.execute("SELECT id FROM recordings").fetchone()["id"]
    conn.executemany(
        """
        INSERT INTO subtitles (
            recording_id, cue_index, start_seconds, end_seconds, text, raw_text, source
        ) VALUES (?, ?, ?, ?, ?, ?, 'arib_caption')
        """,
        [
            (recording_id, 1, 1.0, 2.0, "最初の字幕", "最初の字幕",),
            (recording_id, 2, 3.0, 4.0, "次の字幕", "次の字幕",),
        ],
    )
    conn.commit()
    conn.close()

    main(["--db", str(db_path), "list-subtitles", "--recording-id", str(recording_id)])
    text_output = capsys.readouterr().out
    assert "1\t1.000\t2.000\tarib_caption\t最初の字幕" in text_output
    assert "2\t3.000\t4.000\tarib_caption\t次の字幕" in text_output

    main(
        [
            "--db",
            str(db_path),
            "list-subtitles",
            "--recording-id",
            str(recording_id),
            "--format",
            "json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["recording"]["title"] == "字幕キュー"
    assert [row["cue_index"] for row in payload["subtitles"]] == [1, 2]

    con = sqlite3.connect(db_path)
    columns = [row[1] for row in con.execute("PRAGMA table_info(subtitles)").fetchall()]
    con.close()
    assert "cue_index" in columns


def test_init_db_backfills_missing_subtitle_cue_indexes(tmp_path: Path):
    import sqlite3

    db_path = tmp_path / "test.db"
    recording_path = tmp_path / "recording.m2ts"
    recording_path.write_bytes(b"recording")

    from anicapshelf.db import connect, init_db

    conn = connect(db_path)
    init_db(conn)
    conn.execute(
        """
        INSERT INTO recordings (
            path, filename, extension, size_bytes, title
        ) VALUES (?, 'recording.m2ts', '.m2ts', 1, '既存字幕')
        """,
        (str(recording_path),),
    )
    recording_id = conn.execute("SELECT id FROM recordings").fetchone()["id"]
    conn.executemany(
        """
        INSERT INTO subtitles (
            recording_id, start_seconds, end_seconds, text, raw_text, source
        ) VALUES (?, ?, ?, ?, ?, 'arib_caption')
        """,
        [
            (recording_id, 20.0, 21.0, "二番目", "二番目"),
            (recording_id, 10.0, 11.0, "一番目", "一番目"),
        ],
    )
    conn.commit()
    init_db(conn)
    conn.close()

    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT cue_index, text FROM subtitles ORDER BY cue_index"
    ).fetchall()
    con.close()

    assert rows == [(1, "一番目"), (2, "二番目")]


def test_extract_subtitles_batch_keeps_successes_when_later_recording_fails(
    tmp_path: Path, capsys, monkeypatch
):
    import sqlite3

    db_path = tmp_path / "test.db"
    first = tmp_path / "first.m2ts"
    second = tmp_path / "second.m2ts"
    first.write_bytes(b"recording")
    second.write_bytes(b"recording")

    from anicapshelf.db import connect, init_db

    conn = connect(db_path)
    init_db(conn)
    for path, title in [(first, "成功"), (second, "失敗")]:
        conn.execute(
            """
            INSERT INTO recordings (
                path, filename, extension, size_bytes, title, has_arib_caption
            ) VALUES (?, ?, '.m2ts', 1, ?, 1)
            """,
            (str(path), path.name, title),
        )
    conn.commit()
    conn.close()

    def fake_extract_srt(path, seconds=None, timeout=180):
        if Path(path) == second:
            raise TimeoutError("timeout")
        return (
            "1\n"
            "00:00:01,000 --> 00:00:03,000\n"
            "保存される字幕\n\n"
        )

    monkeypatch.setattr("anicapshelf.cli.extract_srt", fake_extract_srt)

    main(
        [
            "--db",
            str(db_path),
            "extract-subtitles-batch",
            "--only-with-arib",
            "--commit-every",
            "2",
        ]
    )
    output = capsys.readouterr().out

    con = sqlite3.connect(db_path)
    rows = con.execute("SELECT text FROM subtitles").fetchall()
    con.close()

    assert "recordings failed: 1" in output
    assert rows == [("保存される字幕",)]


def test_review_unmatched_outputs_indexed_capture(tmp_path: Path, capsys):
    captures_root = tmp_path / "captures"
    captures_root.mkdir()
    (captures_root / "Capture_20260115-015919.jpg").write_bytes(b"capture")
    db_path = tmp_path / "test.db"

    main(
        [
            "--db",
            str(db_path),
            "scan-captures",
            "--captures-root",
            str(captures_root),
        ]
    )
    capsys.readouterr()
    main(["--db", str(db_path), "review-unmatched", "--limit", "1"])
    output = capsys.readouterr().out

    assert "Capture_20260115-015919.jpg" in output


def test_export_captures_jsonl(tmp_path: Path, capsys):
    captures_root = tmp_path / "captures"
    captures_root.mkdir()
    (captures_root / "Capture_20260115-015919.jpg").write_bytes(b"capture")
    db_path = tmp_path / "test.db"

    main(
        [
            "--db",
            str(db_path),
            "scan-captures",
            "--captures-root",
            str(captures_root),
        ]
    )
    capsys.readouterr()
    main(["--db", str(db_path), "export", "captures", "--format", "jsonl"])
    output = capsys.readouterr().out

    assert '"filename": "Capture_20260115-015919.jpg"' in output


def test_export_captures_csv_file(tmp_path: Path, capsys):
    captures_root = tmp_path / "captures"
    captures_root.mkdir()
    (captures_root / "Capture_20260115-015919.jpg").write_bytes(b"capture")
    db_path = tmp_path / "test.db"
    output_path = tmp_path / "captures.csv"

    main(
        [
            "--db",
            str(db_path),
            "scan-captures",
            "--captures-root",
            str(captures_root),
        ]
    )
    capsys.readouterr()
    main(
        [
            "--db",
            str(db_path),
            "export",
            "captures",
            "--format",
            "csv",
            "--output",
            str(output_path),
        ]
    )

    assert "Capture_20260115-015919.jpg" in output_path.read_text(encoding="utf-8")


def test_match_marks_one_best_candidate(tmp_path: Path, capsys):
    records_root = tmp_path / "records"
    captures_root = tmp_path / "captures"
    records_root.mkdir()
    captures_root.mkdir()
    previous = records_root / "2026年01月10日01時30分00秒-前番組　第１話.m2ts"
    current = records_root / "2026年01月10日02時00分00秒-本命番組　第１話.m2ts"
    capture = captures_root / "Capture_20260110-020004.jpg"
    previous.write_bytes(b"recording")
    current.write_bytes(b"recording")
    capture.write_bytes(b"capture")

    import os
    import sqlite3

    previous_mtime = datetime(2026, 1, 10, 2, 0, 3).timestamp()
    current_mtime = datetime(2026, 1, 10, 2, 30, 0).timestamp()
    capture_mtime = datetime(2026, 1, 10, 2, 0, 4).timestamp()
    os.utime(previous, (previous_mtime, previous_mtime))
    os.utime(current, (current_mtime, current_mtime))
    os.utime(capture, (capture_mtime, capture_mtime))

    db_path = tmp_path / "test.db"
    main(["--db", str(db_path), "scan-records", "--records-root", str(records_root)])
    main(["--db", str(db_path), "scan-captures", "--captures-root", str(captures_root)])
    main(["--db", str(db_path), "match", "--window-minutes", "2"])
    capsys.readouterr()

    con = sqlite3.connect(db_path)
    rows = con.execute(
        """
        SELECT r.title, m.is_best, m.confidence, m.confidence_reason
        FROM capture_recording_matches m
        JOIN recordings r ON r.id = m.recording_id
        ORDER BY m.is_best DESC, r.title
        """
    ).fetchall()
    con.close()

    assert len(rows) == 2
    assert rows[0][0] == "本命番組　第１話"
    assert rows[0][1] == 1
    assert rows[0][2] > rows[1][2]
    assert "inside_recording" in rows[0][3]
    assert "multi_candidate_penalty=2" in rows[0][3]


def test_match_scores_outside_window_lower_than_inside(tmp_path: Path, capsys):
    records_root = tmp_path / "records"
    captures_root = tmp_path / "captures"
    records_root.mkdir()
    captures_root.mkdir()
    recording = records_root / "2026年01月10日02時00分00秒-本命番組　第１話.m2ts"
    capture_inside = captures_root / "Capture_20260110-020500.jpg"
    capture_before = captures_root / "Capture_20260110-015959.jpg"
    recording.write_bytes(b"recording")
    capture_inside.write_bytes(b"capture")
    capture_before.write_bytes(b"capture")

    import os
    import sqlite3

    recording_mtime = datetime(2026, 1, 10, 2, 30, 0).timestamp()
    inside_mtime = datetime(2026, 1, 10, 2, 5, 0).timestamp()
    before_mtime = datetime(2026, 1, 10, 1, 59, 59).timestamp()
    os.utime(recording, (recording_mtime, recording_mtime))
    os.utime(capture_inside, (inside_mtime, inside_mtime))
    os.utime(capture_before, (before_mtime, before_mtime))

    db_path = tmp_path / "test.db"
    main(["--db", str(db_path), "scan-records", "--records-root", str(records_root)])
    main(["--db", str(db_path), "scan-captures", "--captures-root", str(captures_root)])
    main(["--db", str(db_path), "match", "--window-minutes", "2"])
    capsys.readouterr()

    con = sqlite3.connect(db_path)
    rows = con.execute(
        """
        SELECT c.filename, m.confidence, m.confidence_reason
        FROM capture_recording_matches m
        JOIN captures c ON c.id = m.capture_id
        ORDER BY c.filename
        """
    ).fetchall()
    con.close()

    before = next(row for row in rows if row[0] == "Capture_20260110-015959.jpg")
    inside = next(row for row in rows if row[0] == "Capture_20260110-020500.jpg")
    assert inside[1] > before[1]
    assert "inside_recording" in inside[2]
    assert "before_start" in before[2]
