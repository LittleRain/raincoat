"""Single package entry point; management commands do not load native adapters."""
import argparse
import json
import sys
import subprocess
from . import __version__


def main():
    argv=sys.argv[1:]
    if argv==['--version'] or argv==['version']:
        print(__version__);return
    commands={'setup','doctor','update'}
    if not argv or argv[0] in ('-h','--help'):
        print('local-agent '+__version__+'\nCommands: mcp, status, submit, get, wait, cancel, setup, doctor, update\nUse local-agent COMMAND --help for options.');return
    if argv[0] not in commands:
        if sys.platform!='darwin':
            print(json.dumps({'error':'当前运行时后端只支持 macOS。'},ensure_ascii=False),file=sys.stderr);raise SystemExit(1)
        from .bridge import main as bridge_main
        bridge_main();return
    parser=argparse.ArgumentParser(prog='local-agent');sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('setup');p.add_argument('--client',choices=['auto','codex','deepseek','generic','all'],default='auto');p.add_argument('--apply',action='store_true');p.add_argument('--dsh-profile',default='desktop');p.add_argument('--output')
    p=sub.add_parser('doctor');p.add_argument('--backend',choices=['all','bitto','workbuddy','gpt'],default='all');p.add_argument('--install-deps',action='store_true')
    p=sub.add_parser('update');p.add_argument('--check',action='store_true');p.add_argument('--version',dest='target_version');p.add_argument('--from',dest='source')
    args=vars(parser.parse_args(argv));command=args.pop('command')
    try:
        if command=='update':
            from .updates import update
            result=update(**args)
        else:
            from . import management
            result=getattr(management,command)(**args)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if command=='doctor' and not result['healthy']:raise SystemExit(1)
    except (OSError,ValueError,RuntimeError,ImportError,subprocess.SubprocessError) as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False),file=sys.stderr);raise SystemExit(1)
