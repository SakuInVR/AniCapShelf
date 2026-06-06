from __future__ import annotations

import json
from pathlib import Path

from anicapshelf.annotations import save_annotated_capture
from anicapshelf.cli import main
from anicapshelf.db import connect, init_db


def test_save_annotated_capture_stores_source_metadata(tmp_path: Path):
    db_path = tmp_path / "test.db"
    output_root = tmp_path / "captures"
    conn = connect(db_path)
    init_db(conn)

    result = save_annotated_capture(
        conn,
        image_bytes=b"capture image",
        original_filename="capture.jpg",
        output_root=output_root,
        metadata={
            "source_app": "KonomiTV",
            "captured_at": "2026-06-06T12:34:56+09:00",
            "recorded_program_id": 123,
            "recorded_video_id": 456,
            "recording_file_path": "/recorded/anime/example.ts",
            "playback_position_seconds": 78.9,
            "konomitv_url": "http://konomitv.local/videos/watch/123",
            "title": "作品名",
        },
        tags=["SNS候補", "アイキャッチ"],
        note="共有したいカット",
    )

    row = conn.execute(
        """
        SELECT
            c.filename,
            c.source_hint,
            a.source_app,
            a.external_program_id,
            a.external_video_id,
            a.recording_file_path,
            a.playback_position_seconds,
            a.source_url,
            a.tags_json,
            a.note,
            a.metadata_json
        FROM capture_annotations a
        JOIN captures c ON c.id = a.capture_id
        WHERE a.id = ?
        """,
        (result.annotation_id,),
    ).fetchone()

    assert result.image_path.exists()
    assert row["filename"].endswith(".jpg")
    assert row["source_hint"] == "KonomiTV"
    assert row["source_app"] == "KonomiTV"
    assert row["external_program_id"] == "123"
    assert row["external_video_id"] == "456"
    assert row["recording_file_path"] == "/recorded/anime/example.ts"
    assert row["playback_position_seconds"] == 78.9
    assert row["source_url"] == "http://konomitv.local/videos/watch/123"
    assert json.loads(row["tags_json"]) == ["SNS候補", "アイキャッチ"]
    assert row["note"] == "共有したいカット"
    assert json.loads(row["metadata_json"])["title"] == "作品名"
    conn.close()


def test_export_annotations_jsonl(tmp_path: Path, capsys):
    db_path = tmp_path / "test.db"
    output_root = tmp_path / "captures"
    conn = connect(db_path)
    init_db(conn)
    save_annotated_capture(
        conn,
        image_bytes=b"capture image",
        original_filename="capture.png",
        output_root=output_root,
        metadata={
            "source_app": "KonomiTV",
            "recorded_program_id": 123,
            "playback_position_seconds": 12.5,
        },
    )

    main(["--db", str(db_path), "export", "annotations", "--format", "jsonl"])
    output = capsys.readouterr().out

    assert '"source_app": "KonomiTV"' in output
    assert '"playback_position_seconds": 12.5' in output
    conn.close()


def test_show_capture_outputs_annotation_source(tmp_path: Path, capsys):
    db_path = tmp_path / "test.db"
    output_root = tmp_path / "captures"
    conn = connect(db_path)
    init_db(conn)
    result = save_annotated_capture(
        conn,
        image_bytes=b"capture image",
        original_filename="capture.jpg",
        output_root=output_root,
        metadata={
            "source_app": "KonomiTV",
            "recorded_program_id": 123,
            "recording_file_path": "/recorded/anime/example.ts",
            "playback_position_seconds": 12.5,
            "konomitv_url": "http://konomitv.local/videos/watch/123",
            "title": "作品名",
            "episode_number": 5,
            "subtitle": "サブタイトル",
        },
        tags=["SNS候補"],
        note="共有したいカット",
    )
    conn.close()

    main(["--db", str(db_path), "show-capture", str(result.capture_id)])
    output = capsys.readouterr().out

    assert "source_app: KonomiTV" in output
    assert "program_id: 123" in output
    assert "playback_position_seconds: 12.5" in output
    assert "source_url: http://konomitv.local/videos/watch/123" in output
    assert "tags: SNS候補" in output
    assert "title: 作品名 第5話 サブタイトル" in output


def test_show_capture_json_outputs_decoded_metadata(tmp_path: Path, capsys):
    db_path = tmp_path / "test.db"
    output_root = tmp_path / "captures"
    conn = connect(db_path)
    init_db(conn)
    result = save_annotated_capture(
        conn,
        image_bytes=b"capture image",
        original_filename="capture.jpg",
        output_root=output_root,
        metadata={
            "source_app": "KonomiTV",
            "recorded_program_id": 123,
            "playback_position_seconds": 12.5,
            "title": "作品名",
        },
        tags=["SNS候補"],
    )
    conn.close()

    main(["--db", str(db_path), "show-capture", str(result.capture_id), "--format", "json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert payload["capture"]["id"] == result.capture_id
    assert payload["annotations"][0]["metadata"]["title"] == "作品名"
    assert payload["annotations"][0]["tags"] == ["SNS候補"]
