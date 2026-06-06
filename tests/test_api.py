from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from anicapshelf.api import AniCapShelfRequestHandler, AniCapShelfServer


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
