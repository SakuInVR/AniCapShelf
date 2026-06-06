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
