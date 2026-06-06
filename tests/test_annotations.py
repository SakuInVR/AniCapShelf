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


def test_save_annotated_capture_normalizes_tags(tmp_path: Path):
    db_path = tmp_path / "test.db"
    output_root = tmp_path / "captures"
    conn = connect(db_path)
    init_db(conn)

    result = save_annotated_capture(
        conn,
        image_bytes=b"capture image",
        original_filename="capture.jpg",
        output_root=output_root,
        metadata={"source_app": "KonomiTV"},
        tags=[" SNS候補 ", "SNS候補", "", "アイキャッチ"],
    )
    tags_json = conn.execute(
        "SELECT tags_json FROM capture_annotations WHERE id = ?",
        (result.annotation_id,),
    ).fetchone()["tags_json"]
    conn.close()

    assert json.loads(tags_json) == ["SNS候補", "アイキャッチ"]


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
    assert "source_jump:" in output
    assert "open_url: http://konomitv.local/videos/watch/123" in output
    assert "timecode: 0:12" in output
    assert "open_hint: http://konomitv.local/videos/watch/123 を開いて 0:12 に移動" in output
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
    assert payload["source_jump"]["playback_position_seconds"] == 12.5
    assert payload["source_jump"]["timecode"] == "0:12"


def test_annotated_capture_links_nearby_subtitles(tmp_path: Path, capsys):
    db_path = tmp_path / "test.db"
    output_root = tmp_path / "captures"
    recording_path = tmp_path / "records" / "anime.ts"
    recording_path.parent.mkdir()
    recording_path.write_bytes(b"recording")
    conn = connect(db_path)
    init_db(conn)
    conn.execute(
        """
        INSERT INTO recordings (
            path, filename, extension, size_bytes, start_at, end_at, duration_seconds
        ) VALUES (?, ?, '.ts', 9, '2026-06-06T01:00:00', '2026-06-06T01:30:00', 1800)
        """,
        (str(recording_path), recording_path.name),
    )
    recording_id = conn.execute("SELECT id FROM recordings").fetchone()["id"]
    conn.executemany(
        """
        INSERT INTO subtitles (recording_id, start_seconds, end_seconds, text, raw_text, source)
        VALUES (?, ?, ?, ?, ?, 'arib_caption')
        """,
        [
            (recording_id, 90.0, 92.0, "少し前のセリフ", "少し前のセリフ"),
            (recording_id, 100.0, 102.0, "ちょうど近いセリフ", "ちょうど近いセリフ"),
            (recording_id, 120.0, 122.0, "遠いセリフ", "遠いセリフ"),
        ],
    )
    conn.commit()
    result = save_annotated_capture(
        conn,
        image_bytes=b"capture image",
        original_filename="capture.jpg",
        output_root=output_root,
        metadata={
            "source_app": "KonomiTV",
            "recording_file_path": str(recording_path),
            "playback_position_seconds": 99.0,
        },
    )
    linked = conn.execute("SELECT COUNT(*) FROM capture_subtitle_links").fetchone()[0]
    conn.close()

    assert linked == 2
    main(["--db", str(db_path), "show-capture", str(result.capture_id)])
    output = capsys.readouterr().out

    assert "subtitles:" in output
    assert "ちょうど近いセリフ" in output
    assert "少し前のセリフ" in output
    assert "遠いセリフ" not in output


def test_backfill_annotations_from_best_match(tmp_path: Path, capsys):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    init_db(conn)
    capture_path = tmp_path / "captures" / "capture.jpg"
    recording_path = tmp_path / "records" / "anime.ts"
    capture_path.parent.mkdir()
    recording_path.parent.mkdir()
    capture_path.write_bytes(b"capture")
    recording_path.write_bytes(b"recording")
    conn.execute(
        """
        INSERT INTO captures (
            path, filename, extension, size_bytes, captured_at, modified_at, source_hint
        ) VALUES (?, 'capture.jpg', '.jpg', 7, '2026-06-06T01:05:00', '2026-06-06T01:05:00', 'capture')
        """,
        (str(capture_path),),
    )
    conn.execute(
        """
        INSERT INTO recordings (
            path, filename, extension, size_bytes, start_at, end_at, duration_seconds,
            title, normalized_title, series_title, episode_number, subtitle
        ) VALUES (?, 'anime.ts', '.ts', 9, '2026-06-06T01:00:00', '2026-06-06T01:30:00',
            1800, '作品名　第5話　サブタイトル', '作品名 第5話 サブタイトル',
            '作品名', 5, 'サブタイトル')
        """,
        (str(recording_path),),
    )
    capture_id = conn.execute("SELECT id FROM captures").fetchone()["id"]
    recording_id = conn.execute("SELECT id FROM recordings").fetchone()["id"]
    conn.execute(
        """
        INSERT INTO capture_recording_matches (
            capture_id, recording_id, source_time_seconds, confidence, is_best, method
        ) VALUES (?, ?, 300.0, 0.9, 1, 'time-window')
        """,
        (capture_id, recording_id),
    )
    conn.commit()
    conn.close()

    main(
        [
            "--db",
            str(db_path),
            "backfill-annotations",
            "--tag",
            "後追い",
            "--note",
            "既存キャプチャから復元",
        ]
    )
    backfill_output = capsys.readouterr().out
    assert "backfill annotations created: 1" in backfill_output

    main(["--db", str(db_path), "show-capture", str(capture_id)])
    output = capsys.readouterr().out

    assert "source_app: AniCapShelfBackfill" in output
    assert "playback_position_seconds: 300.0" in output
    assert f"recording_file_path: {recording_path}" in output
    assert "tags: 後追い" in output
    assert "note: 既存キャプチャから復元" in output
