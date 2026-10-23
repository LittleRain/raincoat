"""Compatibility installer: install the package with uv, then configure discovered clients."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parent
    uv=shutil.which('uv')
    commands=[[uv or 'uv','tool','install','--force',str(root)],['local-agent','setup','--apply']]
    if not args.apply:print(json.dumps({'commands':commands,'next':'加 --apply 安装和迁移；或直接使用 README 的 wheel 安装方式。'},ensure_ascii=False,indent=2));return
    if not uv:raise SystemExit('先安装 uv：https://docs.astral.sh/uv/getting-started/installation/')
    subprocess.run(commands[0],check=True)
    tools=subprocess.check_output([uv,'tool','dir'],text=True).strip()
    subprocess.run([str(Path(tools)/'raincoat-agent-mcp/bin/local-agent'),'setup','--apply'],check=True)

if __name__=='__main__':main()
