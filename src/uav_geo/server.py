from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .models import CaptureOverrides, ImageAnnotation, ImagePoint
from .service import resolve_capture, solve_annotations

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"
DEFAULT_SAMPLE_ROOT = Path(r"G:\DJIImage\drone_images")
DEFAULT_TDT_TOKEN = "6dc690f8d2b7211561a8b0425ea24b51"


def _list_image_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(
        str(path)
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}
    )


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    sample_root: Path = DEFAULT_SAMPLE_ROOT,
    default_tdt_token: str = DEFAULT_TDT_TOKEN,
) -> None:
    sample_root = sample_root.resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "UavGeoServer/0.1"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/ping":
                self._send_json({"ok": True})
                return
            if parsed.path == "/api/config":
                self._send_json(
                    {
                        "sample_root": str(sample_root),
                        "default_tdt_token": default_tdt_token,
                    }
                )
                return
            if parsed.path == "/api/images":
                params = parse_qs(parsed.query)
                root = Path(params.get("root", [str(sample_root)])[0])
                self._send_json({"images": _list_image_files(root)})
                return
            if parsed.path == "/api/image":
                params = parse_qs(parsed.query)
                image_path = params.get("path", [""])[0]
                self._send_file(Path(image_path))
                return
            if parsed.path == "/api/metadata":
                params = parse_qs(parsed.query)
                image_path = params.get("image_path", [""])[0]
                capture = resolve_capture(image_path=image_path)
                summary = capture.to_summary_dict()
                summary["image_url"] = f"/api/image?path={quote(image_path)}"
                self._send_json(summary)
                return
            self._serve_static(parsed.path)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/solve-annotations":
                self.send_error(HTTPStatus.NOT_FOUND, "Unknown API route.")
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            image_path = payload["image_path"]
            overrides = CaptureOverrides(**payload.get("overrides", {}))
            annotations = [
                ImageAnnotation(
                    annotation_id=str(item["annotation_id"]),
                    kind=item["kind"],
                    label=item.get("label"),
                    vertices=[
                        ImagePoint(u=float(vertex["u"]), v=float(vertex["v"]))
                        for vertex in item["vertices"]
                    ],
                )
                for item in payload["annotations"]
            ]

            capture = resolve_capture(image_path=image_path, overrides=overrides)
            solved = solve_annotations(
                image_path=image_path,
                annotations=annotations,
                overrides=overrides,
            )

            self._send_json(
                {
                    "capture": capture.to_summary_dict(),
                    "annotations": [item.to_dict() for item in solved],
                }
            )

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _send_json(self, payload: object, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path: Path) -> None:
            if not path.exists() or not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "File not found.")
                return
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_static(self, route_path: str) -> None:
            target = "index.html" if route_path in {"/", ""} else route_path.lstrip("/")
            file_path = (WEB_ROOT / target).resolve()
            try:
                file_path.relative_to(WEB_ROOT.resolve())
            except ValueError:
                self.send_error(HTTPStatus.FORBIDDEN, "Forbidden path.")
                return

            if not file_path.exists() or not file_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "Static file not found.")
                return
            self._send_file(file_path)

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving annotation app at http://{host}:{port}")
    print(f"Sample root: {sample_root}")
    server.serve_forever()
