"""Non-secret per-user dependency paths; no DeepSeek Harness dependency."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from . import shared

HELPER_VERSION='0.7.9'


def runtime_file():
    return Path.home()/'.config/raincoat-agent-mcp/runtime.json'


def settings():
    path=runtime_file()
    return shared.read_json(path) if path.exists() else {}


def save_settings(**values):
    shared.atomic_json(runtime_file(),{**settings(),**values})


def helper_root():
    return Path.home()/'.local/share/raincoat-agent-mcp/workbuddy'


def helper_path():
    override=os.environ.get('WORKBUDDY_CREDENTIAL_HELPER') or settings().get('credential_helper')
    if override:return str(Path(override).expanduser()) if Path(override).expanduser().is_file() else None
    root=helper_root()/'node_modules/dsh-workbuddy-connect/lib'
    found=list(root.glob('host-heartbeat-*.js'))
    return str(found[0]) if len(found)==1 else None


def node_binary():
    override=os.environ.get('LOCAL_AGENT_NODE')
    if override:return override if Path(override).is_file() else None
    for value in [settings().get('node'),shutil.which('node')]:
        if value and Path(value).is_file():return value
    return None


def node_check():
    binary=node_binary()
    if not binary:return {'available':False,'error':'WorkBuddy 需要 Node.js 22.19+（22系）或 24+，安装后重新运行 doctor。'}
    try:
        result=subprocess.run([binary,'--version'],capture_output=True,text=True,timeout=10,check=True)
        major,minor,*_=map(int,result.stdout.strip().lstrip('v').split('.'))
        supported=(major==22 and minor>=19) or major>=24
        return {'available':supported,'path':binary,'version':result.stdout.strip(),
                **({} if supported else {'error':'Node 版本不满足凭证辅助模块要求：22.19+（22系）或 24+'})}
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        return {'available':False,'error':str(error)}


def install_workbuddy_helper():
    node=node_check()
    if not node['available']:raise RuntimeError(node['error'])
    npm=Path(node['path']).parent/'npm'
    if not npm.is_file():
        discovered=shutil.which('npm')
        if not discovered:raise RuntimeError('npm 不可用，请安装包含 npm 的 Node.js。')
        npm=Path(discovered)
    prefix=helper_root();prefix.mkdir(parents=True,exist_ok=True,mode=0o700)
    subprocess.run([str(npm),'install','--prefix',str(prefix),'--save-exact','--omit=dev','--ignore-scripts','--no-audit','--no-fund',
                    f'dsh-workbuddy-connect@{HELPER_VERSION}'],check=True,
                   stdout=sys.stderr,env={**os.environ,'PATH':str(Path(node['path']).parent)+os.pathsep+os.environ.get('PATH','')})
    # Discover from the managed prefix even when a stale override was configured.
    matches=list((prefix/'node_modules/dsh-workbuddy-connect/lib').glob('host-heartbeat-*.js'))
    if len(matches)!=1:raise RuntimeError('已安装辅助模块，但入口与预期版本不兼容。')
    save_settings(node=node['path'],credential_helper=str(matches[0]))
    return str(matches[0])
