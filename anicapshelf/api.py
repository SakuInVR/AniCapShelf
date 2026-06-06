from __future__ import annotations

import json
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .annotations import save_annotated_capture
from .db import connect, init_db


class AniCapShelfServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        db_path: str,
        capture_output_root: str | Path,
        allow_origin: str | None = None,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.db_path = db_path
        self.capture_output_root = Path(capture_output_root)
        self.allow_origin = allow_origin


class AniCapShelfRequestHandler(BaseHTTPRequestHandler):
    server: AniCapShelfServer

    def do_GET(self) -> None:
        if self.path == "/health":
            self.write_json(HTTPStatus.OK, {"ok": True, "app": "AniCapShelf"})
            return
        self.write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_OPTIONS(self) -> None:
        if self.path != "/api/captures/annotated":
            self.write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        self.send_response(HTTPStatus.NO_CONTENT.value)
        self.write_cors_headers()
        self.send_header("content-length", "0")
        self.end_headers()

    def do_POST(self) -> None:
        if self.path != "/api/captures/annotated":
            self.write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            payload = self.read_multipart()
            image_item = payload.get("image")
            metadata_item = payload.get("metadata")
            if not isinstance(image_item, UploadedFile):
                raise BadRequest("image field is required")
            if not isinstance(metadata_item, str):
                raise BadRequest("metadata field is required")
            try:
                metadata = json.loads(metadata_item)
            except json.JSONDecodeError as exc:
                raise BadRequest("metadata must be valid JSON") from exc
            if not isinstance(metadata, dict):
                raise BadRequest("metadata must be a JSON object")
            metadata.setdefault("content_type", image_item.content_type)
            tags = parse_optional_tags(payload.get("tags") or payload.get("quick_tags"))
            note_value = payload.get("note")
            note = note_value if isinstance(note_value, str) and note_value else None
            conn = connect(self.server.db_path)
            try:
                init_db(conn)
                result = save_annotated_capture(
                    conn,
                    image_bytes=image_item.content,
                    original_filename=image_item.filename,
                    metadata=metadata,
                    output_root=self.server.capture_output_root,
                    tags=tags,
                    note=note,
                )
            finally:
                conn.close()
            self.write_json(
                HTTPStatus.CREATED,
                {
                    "capture_id": result.capture_id,
                    "annotation_id": result.annotation_id,
                    "image_path": str(result.image_path),
                },
            )
        except BadRequest as exc:
            self.write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self.write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def read_multipart(self) -> dict[str, str | "UploadedFile"]:
        content_type = self.headers.get("content-type")
        if not content_type:
            raise BadRequest("content-type is required")
        if not content_type.lower().startswith("multipart/form-data"):
            raise BadRequest("multipart/form-data is required")
        content_length = int(self.headers.get("content-length", "0"))
        raw_body = self.rfile.read(content_length)
        message = BytesParser(policy=default).parsebytes(
            b"Content-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + raw_body
        )
        if not message.is_multipart():
            raise BadRequest("multipart body is required")
        result: dict[str, str | UploadedFile] = {}
        for part in message.iter_parts():
            key = part.get_param("name", header="content-disposition")
            if not key:
                continue
            filename = part.get_filename()
            content = part.get_payload(decode=True) or b""
            if filename:
                result[str(key)] = UploadedFile(
                    filename=Path(filename).name,
                    content=content,
                    content_type=part.get_content_type() or "application/octet-stream",
                )
            else:
                charset = part.get_content_charset() or "utf-8"
                result[str(key)] = content.decode(charset)
        return result

    def write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.write_cors_headers()
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_cors_headers(self) -> None:
        if not self.server.allow_origin:
            return
        self.send_header("access-control-allow-origin", self.server.allow_origin)
        self.send_header("vary", "Origin")
        self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
        self.send_header("access-control-allow-headers", "content-type")

    def log_message(self, format: str, *args: object) -> None:
        return


class UploadedFile:
    def __init__(self, *, filename: str, content: bytes, content_type: str) -> None:
        self.filename = filename
        self.content = content
        self.content_type = content_type


class BadRequest(Exception):
    pass


def parse_optional_tags(value: str | UploadedFile | None) -> list[str]:
    if value is None or isinstance(value, UploadedFile) or value == "":
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [item.strip() for item in value.split(",") if item.strip()]
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise BadRequest("tags must be a JSON array of strings")
    return parsed


def run_server(
    *,
    host: str,
    port: int,
    db_path: str,
    capture_output_root: str | Path,
    allow_origin: str | None = None,
) -> None:
    server = AniCapShelfServer(
        (host, port),
        AniCapShelfRequestHandler,
        db_path=db_path,
        capture_output_root=capture_output_root,
        allow_origin=allow_origin,
    )
    print(f"AniCapShelf API listening on http://{host}:{port}")
    print(f"capture output root: {Path(capture_output_root)}")
    if allow_origin:
        print(f"allowed browser origin: {allow_origin}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopping AniCapShelf API")
    finally:
        server.server_close()
