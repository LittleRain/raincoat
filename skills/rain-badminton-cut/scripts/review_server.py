#!/usr/bin/env python3
"""Serve a generated review directory and render confirmed edits on localhost."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def handler_for(review_dir: Path):
    class ReviewHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(review_dir), **kwargs)

        def do_POST(self) -> None:
            if self.path != "/render":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1_000_000:
                self.send_json(400, {"error": "Invalid edit payload size"})
                return
            try:
                edits = json.loads(self.rfile.read(length))
                if not isinstance(edits, dict) or edits.get("confirmed") is not True:
                    raise ValueError("Confirmation is required")
                edits_path = review_dir / "edits.json"
                edits_path.write_text(json.dumps(edits, ensure_ascii=False, indent=2), encoding="utf-8")
                output = review_dir / "highlights.mp4"
                result = subprocess.run(
                    [sys.executable, str(SCRIPT_DIR / "render_highlights.py"), str(edits_path), "--out", str(output)],
                    text=True,
                    capture_output=True,
                    timeout=3600,
                )
                if result.returncode:
                    raise ValueError((result.stderr or result.stdout).strip() or "FFmpeg render failed")
            except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
                self.send_json(400, {"error": str(error)})
                return
            self.send_json(200, {"output": output.name})

        def send_json(self, status: int, data: dict[str, str]) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ReviewHandler


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve a Rain Badminton Cut review directory on localhost.")
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    review_dir = args.review_dir.resolve()
    if not (review_dir / "review.html").is_file():
        raise SystemExit(f"review.html not found in {review_dir}")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(review_dir))
    except OSError as error:
        raise SystemExit(f"Could not start local review server on port {args.port}: {error}") from error
    print(f"Review server: http://127.0.0.1:{server.server_port}/review.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nReview server stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
