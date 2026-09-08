#!/usr/bin/env python3
"""Create a reviewable badminton-highlight project from one local video.

This is deliberately a review-first entry point.  It creates candidates and an
HTML review page, but it never renders a final montage without the user's
explicit confirmation in ``edits.json``.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run_script(script: str, *args: str) -> None:
    subprocess.run([sys.executable, str(SCRIPT_DIR / script), *args], check=True)


def source_link(output_dir: Path, source: Path) -> Path:
    """Expose the source beside the review page without copying it."""
    link = output_dir / f"source{source.suffix.lower()}"
    if link.exists() or link.is_symlink():
        if link.resolve() != source:
            raise SystemExit(f"Refusing to replace existing review source: {link}")
        return link
    try:
        link.symlink_to(source)
    except OSError:
        # A relative path still works when review.html is opened from output_dir.
        return source
    return link


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a conservative, editable badminton highlight review."
    )
    parser.add_argument("video", type=Path, help="Local badminton match video")
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Directory for clips.json and review.html (default: <video-stem>-review)",
    )
    parser.add_argument("--window", type=float, default=30.0)
    parser.add_argument("--step", type=float, default=24.0)
    parser.add_argument("--open", action="store_true", help="Open review.html after creation")
    parser.add_argument("--serve", action="store_true", help="Serve the review page and render confirmed edits")
    parser.add_argument("--port", type=int, default=8765, help="Local review-server port")
    args = parser.parse_args()

    video = args.video.expanduser().resolve()
    if not video.is_file():
        raise SystemExit(f"Input video not found: {video}")
    if args.window < 3 or args.step < 1:
        raise SystemExit("--window must be at least 3 seconds and --step at least 1 second")

    output_dir = (args.out_dir or video.with_name(f"{video.stem}-review")).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    run_script("preflight.py")
    review_source = source_link(output_dir, video)
    clips_path = output_dir / "clips.json"
    run_script(
        "analyze_video.py",
        str(video),
        "--out",
        str(clips_path),
        "--window",
        str(args.window),
        "--step",
        str(args.step),
    )
    review_path = output_dir / "review.html"
    run_script(
        "generate_review_html.py",
        str(clips_path),
        "--out",
        str(review_path),
        "--video-src",
        os.path.relpath(review_source, review_path.parent),
    )
    print(f"Review ready: {review_path}")
    if args.serve:
        url = f"http://127.0.0.1:{args.port}/review.html"
        print(f"Open {url}; use the page's 确认并生成合集 button when ready.")
        if args.open:
            subprocess.run(["open", url], check=False)
        subprocess.run([sys.executable, str(SCRIPT_DIR / "review_server.py"), str(output_dir), "--port", str(args.port)], check=True)
    else:
        print("Export edits.json from the page, then run:")
        print(f"  python3 {SCRIPT_DIR / 'render_highlights.py'} {output_dir / 'edits.json'}")
        if args.open:
            subprocess.run(["open", str(review_path)], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
