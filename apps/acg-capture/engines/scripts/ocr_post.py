#!/usr/bin/env python3
"""下载一条微博帖子的官图并做本地 OCR，打印「共N个X赏 / 1次N元」候选行。

用法：
  python3 scripts/ocr_post.py --posts runtime/weibo_7324393029.json --match "Magical Holiday"
  python3 scripts/ocr_post.py --posts ... --match "上弦之贰" --dir runtime/ocr/kimetsu --dump

要点：
  - 竖长图必须切段再 OCR（Vision 对超长图会整体降采样，小字全丢）。
  - 不要只看关键词命中：--match 必须能唯一定位到目标盘，同名不同盘会整盘写错。
  - 输出的是候选，人工/模型判读后再写表；脚本不写表。
"""
import argparse
import json
import os
import re
import subprocess
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OCR_BIN = os.path.join(HERE, "ocrbin")


def build_ocr():
    if os.path.exists(OCR_BIN):
        return OCR_BIN
    src = os.path.join(HERE, "ocr.swift")
    subprocess.run(["swiftc", "-O", src, "-o", OCR_BIN], check=True)
    return OCR_BIN


def ocr(bin_path, image_path):
    r = subprocess.run([bin_path, image_path], capture_output=True, text=True)
    return r.stdout


def download(url, dst):
    if os.path.exists(dst) and os.path.getsize(dst) > 10:
        return True
    subprocess.run(["curl", "-s", "-m", "30", "-o", dst, url])
    return os.path.exists(dst) and os.path.getsize(dst) > 10


def read_post(posts, match, need_pics=5):
    hits = [p for p in posts if match in p.get("text", "") and len(p.get("pics", [])) >= need_pics]
    if not hits:
        sys.exit(f"no post matched {match!r} with >= {need_pics} pics")
    if len(hits) > 1:
        print(f"WARN: {len(hits)} posts matched, using the first", file=sys.stderr)
    return hits[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts", required=True)
    ap.add_argument("--match", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--dump", action="store_true", help="同时打印每张图的完整 OCR 文本")
    args = ap.parse_args()

    bin_path = build_ocr()
    posts = json.load(open(args.posts))
    post = read_post(posts, args.match)
    print(f"POST: {post['text'][:80]}")
    os.makedirs(args.dir, exist_ok=True)

    for i, url in enumerate(post["pics"]):
        src = os.path.join(args.dir, f"{i:02d}.jpg")
        if not download(url, src):
            continue
        im = Image.open(src).convert("L")
        h = im.size[1]
        slices = max(1, min(8, round(h / 1100)))
        for j in range(slices):
            seg = im.crop((0, int(h * j / slices), im.width, int(h * (j + 1) / slices)))
            if seg.height < 350:
                continue
            seg = seg.resize((int(seg.width * 1.6), int(seg.height * 1.6)), Image.LANCZOS)
            tmp = f"/tmp/ocr_{i}_{j}.jpg"
            seg.save(tmp, quality=92)
            text = ocr(bin_path, tmp)
            if args.dump:
                print(f"--- img {i} slice {j} ---\n{text}")
            hits = [l.strip() for l in text.splitlines() if "共" in l or ("次" in l and "元" in l)]
            if hits:
                print(f"{i}.{j} | " + " / ".join(h[:48] for h in hits[:4]))


if __name__ == "__main__":
    main()
