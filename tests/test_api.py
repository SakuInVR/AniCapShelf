from __future__ import annotations

import json
import threading
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
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = post_annotated_capture(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert response["capture_id"] == 1
    assert response["annotation_id"] == 1
    assert Path(response["image_path"]).exists()


def post_annotated_capture(port: int) -> dict:
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
    add_field(parts, boundary, "tags", json.dumps(["SNS候補"], ensure_ascii=False))
    body = b"".join(parts) + f"--{boundary}--\r\n".encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/captures/annotated",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 201
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

