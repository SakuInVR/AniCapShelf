from __future__ import annotations

import json
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

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
        api_token: str | None = None,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.db_path = db_path
        self.capture_output_root = Path(capture_output_root)
        self.allow_origin = allow_origin
        self.api_token = api_token


class AniCapShelfRequestHandler(BaseHTTPRequestHandler):
    server: AniCapShelfServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.write_json(HTTPStatus.OK, {"ok": True, "app": "AniCapShelf"})
            return
        if parsed.path.startswith("/api/") and not self.is_authorized():
            self.write_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        try:
            payload = self.handle_api_get(parsed.path, parse_qs(parsed.query))
        except BadRequest as exc:
            self.write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if payload is not None:
            self.write_json(HTTPStatus.OK, payload)
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
        if not self.is_authorized():
            self.write_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
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

    def handle_api_get(self, path: str, query: dict[str, list[str]]) -> dict[str, Any] | None:
        if path == "/api/recordings":
            return {"recordings": self.fetch_recordings(query)}
        if path == "/api/captures":
            return {"captures": self.fetch_captures(query)}
        if path.startswith("/api/captures/"):
            capture_id = parse_path_int(path, "/api/captures/")
            detail = self.fetch_capture_detail(capture_id)
            if detail is None:
                return {"capture": None}
            return detail
        if path == "/api/matches":
            return {"matches": self.fetch_matches(query)}
        if path == "/api/subtitles":
            return {"subtitles": self.fetch_subtitles(query)}
        if path == "/api/tags":
            return {"tags": self.fetch_tags()}
        if path == "/api/collections":
            return {"collections": self.fetch_collections()}
        return None

    def fetch_recordings(self, query: dict[str, list[str]]) -> list[dict[str, Any]]:
        limit = query_int(query, "limit", 100)
        conn = connect(self.server.db_path)
        try:
            init_db(conn)
            rows = conn.execute(
                """
                SELECT id, path, filename, start_at, end_at, duration_seconds,
                       title, normalized_title, series_title, episode_number,
                       subtitle, has_arib_caption, scanned_at
                FROM recordings
                ORDER BY start_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def fetch_captures(self, query: dict[str, list[str]]) -> list[dict[str, Any]]:
        limit = query_int(query, "limit", 100)
        conn = connect(self.server.db_path)
        try:
            init_db(conn)
            rows = conn.execute(
                """
                SELECT
                    c.id,
                    c.path,
                    c.filename,
                    c.captured_at,
                    c.width,
                    c.height,
                    c.source_hint,
                    best.recording_id,
                    best.source_time_seconds,
                    best.confidence,
                    best.recording_title,
                    ann.tags_json
                FROM captures c
                LEFT JOIN (
                    SELECT
                        m.capture_id,
                        m.recording_id,
                        m.source_time_seconds,
                        m.confidence,
                        r.title AS recording_title
                    FROM capture_recording_matches m
                    JOIN recordings r ON r.id = m.recording_id
                    WHERE m.is_best = 1
                ) best ON best.capture_id = c.id
                LEFT JOIN (
                    SELECT capture_id, tags_json, MAX(id) AS latest_annotation_id
                    FROM capture_annotations
                    GROUP BY capture_id
                ) ann ON ann.capture_id = c.id
                ORDER BY c.captured_at DESC, c.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            captures = []
            for row in rows:
                item = dict(row)
                item["tags"] = json_loads_or_default(item.pop("tags_json", None), [])
                captures.append(item)
            return captures
        finally:
            conn.close()

    def fetch_capture_detail(self, capture_id: int) -> dict[str, Any] | None:
        conn = connect(self.server.db_path)
        try:
            init_db(conn)
            capture = conn.execute("SELECT * FROM captures WHERE id = ?", (capture_id,)).fetchone()
            if capture is None:
                return None
            annotations = [
                decode_annotation_json(dict(row))
                for row in conn.execute(
                    """
                    SELECT *
                    FROM capture_annotations
                    WHERE capture_id = ?
                    ORDER BY id DESC
                    """,
                    (capture_id,),
                ).fetchall()
            ]
            matches = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT m.*, r.path AS recording_path, r.title AS recording_title
                    FROM capture_recording_matches m
                    JOIN recordings r ON r.id = m.recording_id
                    WHERE m.capture_id = ?
                    ORDER BY m.is_best DESC, m.confidence DESC
                    """,
                    (capture_id,),
                ).fetchall()
            ]
            subtitles = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT
                        s.id AS subtitle_id,
                        s.recording_id,
                        s.cue_index,
                        s.start_seconds,
                        s.end_seconds,
                        s.text,
                        s.source,
                        MIN(l.offset_seconds) AS offset_seconds,
                        GROUP_CONCAT(l.method, ',') AS method
                    FROM capture_subtitle_links l
                    JOIN subtitles s ON s.id = l.subtitle_id
                    WHERE l.capture_id = ?
                    GROUP BY s.id, s.recording_id, s.cue_index, s.start_seconds,
                             s.end_seconds, s.text, s.source
                    ORDER BY ABS(MIN(l.offset_seconds)), COALESCE(s.cue_index, s.id)
                    """,
                    (capture_id,),
                ).fetchall()
            ]
            ocr_results = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT *
                    FROM capture_ocr_results
                    WHERE capture_id = ?
                    ORDER BY id DESC
                    """,
                    (capture_id,),
                ).fetchall()
            ]
            collections = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT col.id, col.name, col.description
                    FROM collection_items item
                    JOIN collections col ON col.id = item.collection_id
                    WHERE item.capture_id = ?
                    ORDER BY col.name
                    """,
                    (capture_id,),
                ).fetchall()
            ]
            return {
                "capture": dict(capture),
                "annotations": annotations,
                "matches": matches,
                "subtitles": subtitles,
                "ocr_results": ocr_results,
                "collections": collections,
            }
        finally:
            conn.close()

    def fetch_matches(self, query: dict[str, list[str]]) -> list[dict[str, Any]]:
        capture_id = query_int(query, "capture_id", None)
        where = ""
        params: list[Any] = []
        if capture_id is not None:
            where = "WHERE m.capture_id = ?"
            params.append(capture_id)
        conn = connect(self.server.db_path)
        try:
            init_db(conn)
            rows = conn.execute(
                f"""
                SELECT m.*, c.filename AS capture_filename, r.title AS recording_title,
                       r.path AS recording_path
                FROM capture_recording_matches m
                JOIN captures c ON c.id = m.capture_id
                JOIN recordings r ON r.id = m.recording_id
                {where}
                ORDER BY m.capture_id DESC, m.is_best DESC, m.confidence DESC
                LIMIT 200
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def fetch_subtitles(self, query: dict[str, list[str]]) -> list[dict[str, Any]]:
        recording_id = query_int(query, "recording_id", None)
        if recording_id is None:
            raise BadRequest("recording_id is required")
        limit = query_int(query, "limit", 200)
        conn = connect(self.server.db_path)
        try:
            init_db(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM subtitles
                WHERE recording_id = ?
                ORDER BY COALESCE(cue_index, id), start_seconds, id
                LIMIT ?
                """,
                (recording_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def fetch_tags(self) -> list[dict[str, Any]]:
        conn = connect(self.server.db_path)
        try:
            init_db(conn)
            rows = conn.execute("SELECT tags_json FROM capture_annotations").fetchall()
            counts: dict[str, int] = {}
            for row in rows:
                for tag in json_loads_or_default(row["tags_json"], []):
                    counts[str(tag)] = counts.get(str(tag), 0) + 1
            return [
                {"name": name, "count": count}
                for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            ]
        finally:
            conn.close()

    def fetch_collections(self) -> list[dict[str, Any]]:
        conn = connect(self.server.db_path)
        try:
            init_db(conn)
            rows = conn.execute(
                """
                SELECT
                    col.id,
                    col.name,
                    col.description,
                    col.created_at,
                    COUNT(item.capture_id) AS capture_count
                FROM collections col
                LEFT JOIN collection_items item ON item.collection_id = col.id
                GROUP BY col.id
                ORDER BY col.name
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

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

    def is_authorized(self) -> bool:
        if not self.server.api_token:
            return True
        expected = f"Bearer {self.server.api_token}"
        return self.headers.get("authorization") == expected

    def write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("content-type", "application/json; charset=utf-8")
        if status == HTTPStatus.UNAUTHORIZED:
            self.send_header("www-authenticate", 'Bearer realm="AniCapShelf"')
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
        self.send_header("access-control-allow-headers", "authorization, content-type")

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


def parse_path_int(path: str, prefix: str) -> int:
    value = path.removeprefix(prefix).strip("/")
    if not value.isdigit():
        raise BadRequest("invalid numeric id")
    return int(value)


def query_int(query: dict[str, list[str]], key: str, default: int | None) -> int | None:
    values = query.get(key)
    if not values or values[0] == "":
        return default
    try:
        value = int(values[0])
    except ValueError as exc:
        raise BadRequest(f"{key} must be an integer") from exc
    if value < 1:
        raise BadRequest(f"{key} must be 1 or greater")
    return value


def json_loads_or_default(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def decode_annotation_json(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["tags"] = json_loads_or_default(decoded.pop("tags_json", None), [])
    decoded["metadata"] = json_loads_or_default(decoded.pop("metadata_json", None), {})
    return decoded


def run_server(
    *,
    host: str,
    port: int,
    db_path: str,
    capture_output_root: str | Path,
    allow_origin: str | None = None,
    api_token: str | None = None,
) -> None:
    server = AniCapShelfServer(
        (host, port),
        AniCapShelfRequestHandler,
        db_path=db_path,
        capture_output_root=capture_output_root,
        allow_origin=allow_origin,
        api_token=api_token,
    )
    print(f"AniCapShelf API listening on http://{host}:{port}")
    print(f"capture output root: {Path(capture_output_root)}")
    if allow_origin:
        print(f"allowed browser origin: {allow_origin}")
    if api_token:
        print("API token auth: enabled")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopping AniCapShelf API")
    finally:
        server.server_close()
