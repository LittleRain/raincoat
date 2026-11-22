#!/usr/bin/env python3
"""Create conservative highlight candidates from local motion and audio features.

This deliberately uses only FFmpeg and the standard library.  It does not claim
to recognize shuttlecock strokes; its output is an editable starting point.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import subprocess
import sys
from pathlib import Path


SIGNAL_NAMES = (
    "rally_length",
    "estimated_shot_count",
    "movement_intensity",
    "attack_defense_switch",
    "net_play",
    "audio_energy",
)
WEIGHTS = (0.25, 0.20, 0.20, 0.15, 0.10, 0.10)


def probe(path: Path) -> tuple[float, int, int, bool]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(result.stdout)
    video = next((stream for stream in data["streams"] if stream.get("codec_type") == "video"), None)
    if not video:
        raise SystemExit("Input has no video stream")
    duration = float(data["format"].get("duration", 0))
    if not math.isfinite(duration) or duration <= 0:
        raise SystemExit("Could not determine a valid video duration")
    return duration, int(video["width"]), int(video["height"]), any(
        stream.get("codec_type") == "audio" for stream in data["streams"]
    )


def normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    ordered = sorted(values)
    low = ordered[int((len(ordered) - 1) * 0.10)]
    high = ordered[int((len(ordered) - 1) * 0.90)]
    if high - low < 1e-9:
        return [0.0] * len(values)
    return [max(0.0, min(1.0, (value - low) / (high - low))) for value in values]


def motion_per_second(path: Path, width: int, height: int, duration: float, roi: tuple[float, float, float, float] | None = None) -> list[float]:
    if roi:
        _, _, roi_width, roi_height = roi
        height = max(2, round(height * roi_height))
        width = max(2, round(width * roi_width))
    sample_width = min(160, width)
    sample_height = max(2, round(height * sample_width / width) // 2 * 2)
    frame_size = sample_width * sample_height
    crop = '' if roi is None else f'crop=iw*{roi[2]}:ih*{roi[3]}:iw*{roi[0]}:ih*{roi[1]},'
    process = subprocess.Popen(
        [
            "ffmpeg", "-v", "error", "-i", str(path), "-vf",
            f"fps=1,{crop}scale={sample_width}:{sample_height}", "-pix_fmt", "gray",
            "-f", "rawvideo", "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    values: list[float] = []
    previous: bytes | None = None
    assert process.stdout is not None
    while True:
        frame = process.stdout.read(frame_size)
        if len(frame) != frame_size:
            break
        if previous is None:
            values.append(0.0)
        else:
            values.append(sum(abs(a - b) for a, b in zip(frame[::8], previous[::8])) / (255 * len(frame[::8])))
        previous = frame
    stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
    if process.wait() != 0:
        raise SystemExit(f"Could not extract motion features: {stderr.strip()}")
    return (values + [0.0] * math.ceil(duration))[: math.ceil(duration)]


def audio_per_second(path: Path, duration: float) -> list[float]:
    sample_rate = 8000
    chunk_size = sample_rate * 4
    process = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    values: list[float] = []
    assert process.stdout is not None
    while True:
        chunk = process.stdout.read(chunk_size)
        if not chunk:
            break
        floats = array.array("f")
        floats.frombytes(chunk[: len(chunk) - len(chunk) % 4])
        if sys.byteorder != "little":
            floats.byteswap()
        samples = floats[::16]
        values.append(math.sqrt(sum(value * value for value in samples) / len(samples)) if samples else 0.0)
    stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
    if process.wait() != 0:
        raise SystemExit(f"Could not extract audio features: {stderr.strip()}")
    return (values + [0.0] * math.ceil(duration))[: math.ceil(duration)]


def merge_ranges(ranges: list[tuple[float, float]], gap: float) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1] + gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def active_ranges(activity: list[float], pre_roll: float, post_roll: float, total: float, minimum: float) -> list[tuple[float, float]]:
    if not activity or max(activity) <= 0:
        return []
    threshold = sorted(activity)[int((len(activity) - 1) * 0.60)]
    threshold = max(0.25, threshold)
    raw: list[tuple[float, float]] = []
    start: int | None = None
    for second, value in enumerate(activity + [0.0]):
        if value >= threshold and start is None:
            start = second
        elif value < threshold and start is not None:
            raw.append((float(start), float(second)))
            start = None
    # Group short pauses before adding context. Merging padded ranges would join
    # separate rallies whenever their safety margins touch.
    groups = merge_ranges(raw, gap=1.0)
    expanded = [[max(0.0, start - pre_roll), min(total, end + post_roll)] for start, end in groups]
    for index in range(len(expanded) - 1):
        if expanded[index][1] > expanded[index + 1][0]:
            boundary = (groups[index][1] + groups[index + 1][0]) / 2
            expanded[index][1] = boundary
            expanded[index + 1][0] = boundary
    return [(start, end) for start, end in expanded if end - start >= minimum]


def fallback_ranges(total: float, window: float, step: float) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    start = 0.0
    while start < total:
        end = min(total, start + window)
        if end - start >= 3.0:
            ranges.append((start, end))
        if end >= total:
            break
        start += step
    return ranges


def mean(values: list[float], start: float, end: float) -> float:
    selected = values[max(0, int(math.floor(start))) : max(0, int(math.ceil(end)))]
    return sum(selected) / len(selected) if selected else 0.0


def candidate(identifier: int, start: float, end: float, motion: list[float], audio: list[float], fallback: bool) -> dict:
    duration = end - start
    motion_signal = mean(motion, start, end)
    audio_signal = mean(audio, start, end)
    part = motion[max(0, int(start)) : max(0, int(math.ceil(end)))]
    switches = sum(abs(right - left) for left, right in zip(part, part[1:])) / max(1, len(part) - 1)
    signals = {
        "rally_length": min(1.0, duration / 30.0),
        "estimated_shot_count": min(1.0, 0.20 + motion_signal * 0.80),
        "movement_intensity": motion_signal,
        "attack_defense_switch": min(1.0, switches * 3.0),
        "net_play": 0.0,
        "audio_energy": audio_signal,
    }
    score = round(100 * sum(WEIGHTS[index] * signals[name] for index, name in enumerate(SIGNAL_NAMES)), 1)
    reasons = ["本地运动量与音频能量检测到活跃片段"]
    confidence = 0.62
    if fallback:
        reasons = ["未检测到可靠活动边界，使用保守候选窗口"]
        confidence = 0.40
    return {
        "id": f"rally-{identifier:03d}", "start": round(start, 3), "end": round(end, 3),
        "duration": round(duration, 3), "score": score,
        "completeness_confidence": confidence, "signals": signals, "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", type=Path, default=Path("clips.json"))
    parser.add_argument("--window", type=float, default=30.0, help="Fallback candidate-window duration")
    parser.add_argument("--step", type=float, default=24.0, help="Fallback candidate-window step")
    parser.add_argument("--pre-roll", type=float, default=2.0)
    parser.add_argument("--post-roll", type=float, default=3.0)
    parser.add_argument("--min-duration", type=float, default=3.0)
    parser.add_argument("--court-roi", type=float, nargs=4, metavar=("X", "Y", "W", "H"),
                        help="Normalized court area to analyze, e.g. 0.1 0.2 0.8 0.7")
    parser.add_argument("--ignore-before", type=float, default=0.0,
                        help="Ignore camera setup before this source-video second")
    args = parser.parse_args()
    video = args.video.expanduser().resolve()
    if not video.is_file():
        raise SystemExit(f"Input not found: {video}")
    total, width, height, has_audio = probe(video)
    roi = tuple(args.court_roi) if args.court_roi else None
    if roi:
        x, y, w, h = roi
        if not all(math.isfinite(v) for v in roi) or x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 1 or y + h > 1:
            raise SystemExit("--court-roi must be normalized X Y W H within the video")
    if not math.isfinite(args.ignore_before) or not 0 <= args.ignore_before < total:
        raise SystemExit("--ignore-before must be within the source video")
    if any(not math.isfinite(value) or value < 0 for value in (args.pre_roll, args.post_roll)) or not math.isfinite(args.min_duration) or args.min_duration <= 0:
        raise SystemExit("Safety margins must be non-negative and minimum duration must be positive")
    motion = normalize(motion_per_second(video, width, height, total, roi))
    audio = normalize(audio_per_second(video, total)) if has_audio else [0.0] * len(motion)
    activity = [0.9 * movement + 0.1 * sound for movement, sound in zip(motion, audio)]
    for second in range(math.ceil(args.ignore_before)):
        activity[second] = 0.0
    ranges = active_ranges(activity, args.pre_roll, args.post_roll, total, args.min_duration)
    ranges = [(max(args.ignore_before, start), end) for start, end in ranges if end - max(args.ignore_before, start) >= args.min_duration]
    fallback = not ranges
    if fallback:
        ranges = [(max(args.ignore_before, start), end) for start, end in fallback_ranges(total, max(3.0, args.window), max(1.0, args.step))
                  if end - max(args.ignore_before, start) >= args.min_duration]
    candidates = [candidate(index, start, end, motion, audio, fallback) for index, (start, end) in enumerate(ranges, 1)]
    # Review in source order; ranking is only used for optional top-N preselection.
    result = {
        "source": str(video), "duration": total,
        "provider": "local-heuristic" if not fallback else "baseline-window-fallback",
        "feature_summary": {"motion_samples": len(motion), "audio_samples": len(audio), "used_fallback": fallback,
                            "court_roi": roi, "ignore_before": args.ignore_before},
        "candidates": candidates,
    }
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(candidates)} candidates to {args.out} ({result['provider']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
