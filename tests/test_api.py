from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from anicapshelf.api import AniCapShelfRequestHandler, AniCapShelfServer
from anicapshelf.db import connect, init_db


def test_annotated_capture_api_accepts_multipart_post(tmp_path: Path):
    server = AniCapShelfServer(
        ("127.0.0.1", 0),
        AniCapShelfRequestHandler,
        db_path=str(tmp_path / "api.db"),
        capture_output_root=tmp_path / "captures",
        allow_origin="http://127.0.0.1:7000",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = post_annotated_capture(
            server.server_address[1],
            expected_allow_origin="http://127.0.0.1:7000",
        )
        options_request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/captures/annotated",
            method="OPTIONS",
        )
        with urllib.request.urlopen(options_request, timeout=5) as options_response:
            assert "authorization" in options_response.headers[
                "access-control-allow-headers"
            ]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert response["capture_id"] == 1
    assert response["annotation_id"] == 1
    assert Path(response["image_path"]).exists()


def test_annotated_capture_api_accepts_quick_tags(tmp_path: Path):
    server = AniCapShelfServer(
        ("127.0.0.1", 0),
        AniCapShelfRequestHandler,
        db_path=str(tmp_path / "api.db"),
        capture_output_root=tmp_path / "captures",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = post_annotated_capture(
            server.server_address[1],
            tag_field="quick_tags",
            tag_value="SNS候補, アイキャッチ",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert response["capture_id"] == 1


def test_annotated_capture_api_requires_bearer_token_when_configured(tmp_path: Path):
    server = AniCapShelfServer(
        ("127.0.0.1", 0),
        AniCapShelfRequestHandler,
        db_path=str(tmp_path / "api.db"),
        capture_output_root=tmp_path / "captures",
        api_token="secret-token",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        try:
            post_annotated_capture(server.server_address[1])
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
            assert exc.headers["www-authenticate"] == 'Bearer realm="AniCapShelf"'
        else:
            raise AssertionError("request without token should be rejected")
        response = post_annotated_capture(server.server_address[1], api_token="secret-token")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert response["capture_id"] == 1


def test_api_exposes_archive_read_models(tmp_path: Path):
    db_path = tmp_path / "api.db"
    capture_path = tmp_path / "captures" / "capture.jpg"
    recording_path = tmp_path / "records" / "anime.ts"
    capture_path.parent.mkdir()
    recording_path.parent.mkdir()
    capture_path.write_bytes(b"capture")
    recording_path.write_bytes(b"recording")
    conn = connect(db_path)
    init_db(conn)
    conn.execute(
        """
        INSERT INTO recordings (
            path, filename, extension, size_bytes, title, series_title, episode_number
        ) VALUES (?, 'anime.ts', '.ts', 9, '魔法少女 第5話', '魔法少女', 5)
        """,
        (str(recording_path),),
    )
    recording_id = conn.execute("SELECT id FROM recordings").fetchone()["id"]
    conn.execute(
        """
        INSERT INTO captures (
            path, filename, extension, size_bytes, captured_at, modified_at, source_hint
        ) VALUES (?, 'capture.jpg', '.jpg', 7, '2026-06-06T01:05:00',
                  '2026-06-06T01:05:00', 'capture')
        """,
        (str(capture_path),),
    )
    capture_id = conn.execute("SELECT id FROM captures").fetchone()["id"]
    conn.execute(
        """
        INSERT INTO capture_recording_matches (
            capture_id, recording_id, source_time_seconds, confidence, is_best, method
        ) VALUES (?, ?, 300, 0.95, 1, 'test')
        """,
        (capture_id, recording_id),
    )
    conn.execute(
        """
        INSERT INTO capture_annotations (
            capture_id, source_app, tags_json, metadata_json, note
        ) VALUES (?, 'test', '["SNS候補", "アイキャッチ"]', '{"title":"魔法少女"}', 'メモ')
        """,
        (capture_id,),
    )
    conn.execute(
        """
        INSERT INTO subtitles (
            recording_id, cue_index, start_seconds, end_seconds, text, raw_text, source
        ) VALUES (?, 1, 300, 302, '変身シーン', '変身シーン', 'arib_caption')
        """,
        (recording_id,),
    )
    subtitle_id = conn.execute("SELECT id FROM subtitles").fetchone()["id"]
    conn.execute(
        """
        INSERT INTO capture_subtitle_links (
            capture_id, subtitle_id, offset_seconds, method
        ) VALUES (?, ?, 0, 'test')
        """,
        (capture_id, subtitle_id),
    )
    conn.execute(
        """
        INSERT INTO capture_ocr_results (
            capture_id, engine, text, raw_text, language
        ) VALUES (?, 'tesseract', 'アイキャッチ', 'アイキャッチ', 'jpn')
        """,
        (capture_id,),
    )
    conn.execute(
        "INSERT INTO collections (name, description) VALUES ('名シーン', '保存版')"
    )
    collection_id = conn.execute("SELECT id FROM collections").fetchone()["id"]
    conn.execute(
        "INSERT INTO collection_items (collection_id, capture_id) VALUES (?, ?)",
        (collection_id, capture_id),
    )
    conn.commit()
    conn.close()

    server = AniCapShelfServer(
        ("127.0.0.1", 0),
        AniCapShelfRequestHandler,
        db_path=str(db_path),
        capture_output_root=tmp_path / "captures",
        api_token="secret-token",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        try:
            get_json(server.server_address[1], "/api/captures")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("GET API should require token when configured")
        recordings = get_json(
            server.server_address[1], "/api/recordings", api_token="secret-token"
        )
        captures = get_json(server.server_address[1], "/api/captures", api_token="secret-token")
        detail = get_json(
            server.server_address[1], f"/api/captures/{capture_id}", api_token="secret-token"
        )
        subtitles = get_json(
            server.server_address[1],
            f"/api/subtitles?recording_id={recording_id}",
            api_token="secret-token",
        )
        tags = get_json(server.server_address[1], "/api/tags", api_token="secret-token")
        collections = get_json(
            server.server_address[1], "/api/collections", api_token="secret-token"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert recordings["recordings"][0]["title"] == "魔法少女 第5話"
    assert captures["captures"][0]["tags"] == ["SNS候補", "アイキャッチ"]
    assert detail["capture"]["filename"] == "capture.jpg"
    assert detail["matches"][0]["recording_title"] == "魔法少女 第5話"
    assert detail["subtitles"][0]["text"] == "変身シーン"
    assert detail["ocr_results"][0]["text"] == "アイキャッチ"
    assert detail["collections"][0]["name"] == "名シーン"
    assert subtitles["subtitles"][0]["cue_index"] == 1
    assert tags["tags"][0] == {"name": "SNS候補", "count": 1}
    assert collections["collections"][0]["capture_count"] == 1


def get_json(port: int, path: str, *, api_token: str | None = None) -> dict:
    headers = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200
        return json.loads(response.read().decode("utf-8"))


def post_annotated_capture(
    port: int,
    *,
    tag_field: str = "tags",
    tag_value: str | None = None,
    expected_allow_origin: str | None = None,
    api_token: str | None = None,
) -> dict:
    boundary = "----AniCapShelf" + uuid.uuid4().hex
    metadata = json.dumps(
        {
            "source_app": "KonomiTV",
            "recorded_program_id": 1,
            "playback_position_seconds": 3.5,
        },
        ensure_ascii=False,
    )
    parts: list[bytes] = []
    add_file(parts, boundary, "image", "capture.jpg", b"api image", "image/jpeg")
    add_field(parts, boundary, "metadata", metadata)
    add_field(parts, boundary, tag_field, tag_value or json.dumps(["SNS候補"], ensure_ascii=False))
    body = b"".join(parts) + f"--{boundary}--\r\n".encode("utf-8")
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/captures/annotated",
        data=body,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 201
        if expected_allow_origin:
            assert response.headers["access-control-allow-origin"] == expected_allow_origin
        return json.loads(response.read().decode("utf-8"))


def add_field(parts: list[bytes], boundary: str, name: str, value: str) -> None:
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
        f"{value}\r\n".encode("utf-8")
    )


def add_file(
    parts: list[bytes],
    boundary: str,
    name: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> None:
    header = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
        f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'
    )
    parts.append(header.encode("utf-8") + content + b"\r\n")
