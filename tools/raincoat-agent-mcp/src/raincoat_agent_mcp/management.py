"""Client setup and local environment diagnostics."""
from datetime import datetime
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import sys
from . import __version__, client_config, dependencies

BACKENDS = ('bitto', 'workbuddy', 'gpt')


def canonical_backend(backend):
    if backend == 'codex':
        return 'gpt'
    if backend not in BACKENDS:
        raise ValueError('backend must be bitto, workbuddy, gpt or codex')
    return backend


def probe_backend(backend):
    """Inspect local readiness without changing settings or making model calls."""
    backend = canonical_backend(backend)
    if backend == 'bitto':
        from . import bitto

        result = {'backend': backend, 'runtime': 'existing Bitto local sidecar',
                  'desktop_task_visible': True, 'supports_read_only': False,
                  'login_status': 'unknown', 'authentication_checked': False,
                  'available': False}
        try:
            result['ws_url'] = bitto.discover_ws()
        except (OSError, ValueError, RuntimeError) as error:
            return {**result, 'availability': 'runtime_unavailable', 'error': str(error)}
        try:
            bitto.token()
        except (OSError, ValueError, RuntimeError) as error:
            return {**result, 'availability': 'login_required', 'error': str(error)}
        try:
            result['default_model'] = bitto.settings_model()
        except (OSError, ValueError):
            result['default_model'] = None
        return {**result, 'available': True, 'availability': 'ready',
                'note': '检测到本地运行时和凭证，登录有效性在提交时验证。'}

    if backend == 'workbuddy':
        from . import workbuddy

        status = workbuddy.status()
        node = dependencies.node_check()
        helper = dependencies.helper_path()
        availability = 'not_installed'
        if status['installed']:
            availability = 'ready' if node['available'] and helper else 'missing_dependencies'
        return {**status, 'backend': backend, 'available': availability == 'ready',
                'availability': availability, 'node': node, 'credential_helper': helper,
                'login_status': 'unknown', 'authentication_checked': False, 'supports_read_only': False,
                'next': '安装并登录 WorkBuddy；缺辅助模块时运行 doctor --backend workbuddy --install-deps。'}

    from . import gpt

    status = gpt.status()
    auth = gpt.authentication() if status['installed'] else {'authenticated': False}
    availability = 'not_installed'
    if status['installed']:
        availability = 'ready' if auth['authenticated'] else 'login_required'
    return {**status, **auth, 'backend': backend, 'available': availability == 'ready',
            'availability': availability, 'authentication_checked': status['installed'],
            'login_status': 'verified' if auth['authenticated'] else 'unknown' if not status['installed'] else 'unverified',
            'supports_read_only': True, 'next': '安装 Codex CLI 并执行 codex login。'}


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
    updates={path:render(path.read_text(encoding='utf-8') if path.exists() else '',command,args) for path,render in selected}
    if apply:
        stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        for path,text in updates.items():client_config.write_backed_up(path,text,stamp)
    return {'apply':apply,'files':[str(p) for p in updates],'command':command,'args':args,'next':'重载 MCP 或重启对应客户端。' if apply else '确认后加 --apply 写入，原配置会备份。'}


def doctor(backend='all',install_deps=False):
    selected = BACKENDS if backend == 'all' else (canonical_backend(backend),)
    if install_deps and 'workbuddy' not in selected:
        raise ValueError('--install-deps 仅用于 WorkBuddy')
    report = {'version': __version__, 'platform': platform.system(),
              'python': platform.python_version(), 'backends': {}}
    if sys.platform not in ('darwin','win32'):
        return {**report,'healthy':False,'error':'当前后端只支持 macOS 和 Windows；尚未适配 Linux。'}
    if install_deps:
        dependencies.install_workbuddy_helper()
    for name in selected:
        result = probe_backend(name)
        report['backends'][name] = result
        if name == 'workbuddy' and result['node']['available']:
            dependencies.save_settings(node=result['node']['path'])
        if name == 'gpt' and result['codex']:
            dependencies.save_settings(codex=result['codex'])
    return {**report, 'healthy': all(result['available'] for result in report['backends'].values())}
