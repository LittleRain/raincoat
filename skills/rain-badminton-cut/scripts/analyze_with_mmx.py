#!/usr/bin/env python3
"""Analyze sampled images with mmx vision describe and save raw responses."""
from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("mmx-analysis.json"))
    ap.add_argument("--prompt", default="这是羽毛球比赛画面。请用 JSON 返回：是否处于回合中、是否准备发球、是否死球/回合结束、画面是否清晰，并说明依据。不要输出 Markdown。")
    args=ap.parse_args(); results=[]
    for image in args.images:
        p=subprocess.run(["mmx","vision","describe","--image",str(image),"--prompt",args.prompt],text=True,capture_output=True)
        results.append({"image":str(image),"returncode":p.returncode,"output":p.stdout.strip(),"error":p.stderr.strip()})
    args.out.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Wrote {len(results)} MiniMax responses to {args.out}")

if __name__ == "__main__": main()
