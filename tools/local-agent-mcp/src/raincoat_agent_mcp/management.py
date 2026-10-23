"""Client setup and local environment diagnostics."""
from datetime import datetime
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import sys
from . import __version__, client_config, dependencies


def setup(client='auto',apply=False,dsh_profile='desktop',output=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',dsh_profile):raise ValueError('Invalid DeepSeek Harness profile name')
    command=sys.executable;args=['-m','raincoat_agent_mcp','mcp']
    generic={'mcpServers':{'local_agents':{'command':command,'args':args}}}
    if client=='generic':
        if output:
            path=Path(output).expanduser()
            if apply:client_config.write_backed_up(path,json.dumps(generic,indent=2)+'\n',datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            return {'apply':apply,'output':str(path),'config':generic}
        return generic
    home=Path.home();codex=home/'.codex/config.toml';dsh=home/'.dsh/profiles'/dsh_profile/'cordis.patch.yml'
    selected=[]
    if client in ('codex','all') or (client=='auto' and codex.parent.exists()):selected.append((codex,client_config.codex_config))
    if client in ('deepseek','all') or (client=='auto' and dsh.parent.exists()):selected.append((dsh,client_config.dsh_config))
    if not selected:raise RuntimeError('未发现客户端；指定 --client codex/deepseek，或用 --client generic 生成通用配置。')
    if apply:
        try:
            installed=Path(importlib.metadata.distribution('raincoat-agent-mcp').locate_file('raincoat_agent_mcp/management.py')).resolve()
            if installed!=Path(__file__).resolve():raise importlib.metadata.PackageNotFoundError
        except importlib.metadata.PackageNotFoundError:
            raise RuntimeError('先安装发行包，再从安装后的 local-agent setup --apply 写入稳定配置。') from None
    updates={path:render(path.read_text() if path.exists() else '',command,args) for path,render in selected}
    if apply:
        stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        for path,text in updates.items():client_config.write_backed_up(path,text,stamp)
    return {'apply':apply,'files':[str(p) for p in updates],'command':command,'args':args,'next':'重载 MCP 或重启对应客户端。' if apply else '确认后加 --apply 写入，原配置会备份。'}


def doctor(backend='all',install_deps=False):
    if install_deps and backend=='bitto':raise ValueError('--install-deps 仅用于 WorkBuddy')
    report={'version':__version__,'platform':platform.system(),'python':platform.python_version(),'backends':{}}
    if sys.platform!='darwin':
        return {**report,'healthy':False,'error':'当前 Bitto/WorkBuddy 后端只支持 macOS；尚未适配 Windows/Linux。'}
    if install_deps:dependencies.install_workbuddy_helper()
    healthy=True
    if backend in ('bitto','all'):
        try:
            from . import bitto
            bitto.token()
            report['backends']['bitto']={'available':True,'ws_url':bitto.discover_ws()}
        except (OSError,ValueError,RuntimeError) as error:
            report['backends']['bitto']={'available':False,'error':str(error)};healthy=False
    if backend in ('workbuddy','all'):
        from . import workbuddy
        node=dependencies.node_check();helper=dependencies.helper_path();status=workbuddy.status()
        available=bool(status['installed'] and node['available'] and helper)
        report['backends']['workbuddy']={**status,'available':available,'node':node,'credential_helper':helper,
            'authentication_checked':False,'next':'安装并登录 WorkBuddy；缺辅助模块时运行 doctor --backend workbuddy --install-deps。'}
        healthy=healthy and available
        if node['available']:dependencies.save_settings(node=node['path'])
    return {**report,'healthy':healthy}
