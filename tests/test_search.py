from __future__ import annotations

import json
from pathlib import Path

from anicapshelf.annotations import save_annotated_capture
from anicapshelf.cli import main
from anicapshelf.db import connect, init_db


def test_search_text_finds_recordings_subtitles_and_annotations(tmp_path: Path, capsys):
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
            path, filename, extension, size_bytes, start_at, end_at, duration_seconds,
            title, normalized_title, series_title, episode_number, subtitle
        ) VALUES (?, 'anime.ts', '.ts', 9, '2026-06-06T01:00:00', '2026-06-06T01:30:00',
            1800, '魔法少女　第5話　約束', '魔法少女 第5話 約束', '魔法少女', 5, '約束')
        """,
        (str(recording_path),),
    )
    recording_id = conn.execute("SELECT id FROM recordings").fetchone()["id"]
    conn.execute(
        """
        INSERT INTO subtitles (recording_id, start_seconds, end_seconds, text, raw_text, source)
        VALUES (?, 100, 102, '時間遡行者 暁美ほむら', '時間遡行者 暁美ほむら', 'arib_caption')
        """,
        (recording_id,),
    )
    conn.execute(
        """
        INSERT INTO subtitles (recording_id, start_seconds, end_seconds, text, raw_text, source)
        VALUES (?, 120, 122, 'ＭＡＧＩＡ・レコード！', 'ＭＡＧＩＡ・レコード！', 'arib_caption')
        """,
        (recording_id,),
    )
    save_annotated_capture(
        conn,
        image_bytes=b"capture image",
        original_filename="capture.jpg",
        output_root=output_root,
        metadata={
            "source_app": "KonomiTV",
            "title": "魔法少女",
            "episode_number": 5,
            "subtitle": "約束",
            "recording_file_path": str(recording_path),
            "playback_position_seconds": 100.0,
        },
        tags=["SNS候補", "名シーン"],
        note="共有したいカット",
    )
    conn.execute(
        """
        INSERT INTO capture_ocr_results (
            capture_id, engine, text, raw_text, language
        ) VALUES (1, 'tesseract', 'EDカード 提供バック', 'ＥＤカード・提供バック', 'jpn+eng')
        """
    )
    conn.commit()
    conn.close()

    main(["--db", str(db_path), "rebuild-search-index"])
    rebuild_output = capsys.readouterr().out
    assert "recordings_indexed: 1" in rebuild_output
    assert "subtitles_indexed: 2" in rebuild_output
    assert "annotations_indexed: 1" in rebuild_output
    assert "ocr_indexed: 1" in rebuild_output

    main(["--db", str(db_path), "search-text", "魔法少女"])
    title_output = capsys.readouterr().out
    assert "recording" in title_output
    assert "魔法少女" in title_output

    main(["--db", str(db_path), "search-title", "魔法少女"])
    search_title_output = capsys.readouterr().out
    assert "recording" in search_title_output
    assert "魔法少女" in search_title_output

    main(["--db", str(db_path), "search-text", "暁美ほむら"])
    subtitle_output = capsys.readouterr().out
    assert "subtitle" in subtitle_output
    assert "暁美ほむら" in subtitle_output

    main(["--db", str(db_path), "search-text", "ＭＡＧＩＡ・レコード！"])
    normalized_output = capsys.readouterr().out
    assert "subtitle" in normalized_output
    assert "[MAGIA]" in normalized_output
    assert "[レコード]" in normalized_output

    main(["--db", str(db_path), "search-text", "ＥＤカード"])
    ocr_output = capsys.readouterr().out
    assert "ocr" in ocr_output
    assert "[EDカード]" in ocr_output

    main(["--db", str(db_path), "search-text", "SNS候補", "--format", "json"])
    tag_output = capsys.readouterr().out
    payload = json.loads(tag_output)
    assert payload[0]["entity_type"] == "annotation"
    assert payload[0]["capture_id"] == 1

    main(["--db", str(db_path), "near-capture", "1"])
    near_output = capsys.readouterr().out
    assert "暁美ほむら" in near_output
