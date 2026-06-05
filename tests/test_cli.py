from __future__ import annotations

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
