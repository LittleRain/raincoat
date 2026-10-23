"""Explicit upgrades for uv-managed installs. No auto-updates inside MCP calls."""
import email.parser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from packaging.version import Version
from . import __version__, shared

PACKAGE='raincoat-agent-mcp'


def check_update():
    try:
        request=urllib.request.Request(f'https://pypi.org/pypi/{PACKAGE}/json',headers={'Accept':'application/json'})
        with urllib.request.urlopen(request,timeout=10) as response:
            data=json.load(response)
    except urllib.error.HTTPError as error:
        error.close()
        if error.code==404:raise RuntimeError('包尚未发布到 PyPI；请使用 update --from /path/to/new.whl。') from None
        raise RuntimeError(f'版本检查失败：HTTP {error.code}') from None
    except (OSError,ValueError) as error:
        raise RuntimeError(f'无法检查 PyPI 版本；当前安装仍可使用：{error}') from None
    latest=str(Version(data['info']['version']))
    return {'current_version':__version__,'latest_version':latest,'update_available':Version(latest)>Version(__version__),
            'source':'https://pypi.org','next':'local-agent update，然后重载 MCP。'}


def ensure_idle():
    for path in (shared.STATE/'jobs').glob('*/state.json'):
        try:state=shared.get_task(path.parent.name)
        except (OSError,ValueError,KeyError) as error:
            raise RuntimeError(f'无法确认任务状态，暂不更新：{path.parent.name}') from error
        if state['status'] not in shared.TERMINAL:
            raise RuntimeError(f'仍有执行中或等待授权的任务 {path.parent.name}；完成或取消后再更新。')


def wheel_version(path):
    with zipfile.ZipFile(path) as archive:
        entries=[name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
        if len(entries)!=1:raise ValueError('无效的 wheel 元数据')
        metadata=email.parser.Parser().parsestr(archive.read(entries[0]).decode())
        if re.sub('[-_.]+','-',metadata['Name']).lower()!=PACKAGE:raise ValueError('请选择 raincoat-agent-mcp 的 wheel')
        return str(Version(metadata['Version']))


def update(*,check=False,target_version=None,source=None):
    if check:
        if source or target_version:raise ValueError('--check 不能与 --from/--version 同用')
        return check_update()
    if not (Path(sys.prefix)/'uv-receipt.toml').is_file():
        raise RuntimeError('update 仅支持 uv tool 管理的安装；先用 uv tool install --force 安装发行包。')
    uv=shutil.which('uv')
    if not uv:raise RuntimeError('找不到 uv，请将 uv 加入 PATH 后重试。')
    if source and target_version:raise ValueError('--from 与 --version 不能同时使用')
    ensure_idle()
    target=PACKAGE
    if source:
        path=Path(source).expanduser().resolve()
        if not path.is_file() or path.suffix!='.whl':raise ValueError('--from 需要本地 .whl 文件')
        target_version=wheel_version(path)
        target=str(path)
    elif target_version:
        target_version=str(Version(target_version));target+=f'=={target_version}'
    # Reinstall an explicit spec: a wheel/old version constraint must not pin future upgrades.
    result=subprocess.run([uv,'tool','install','--force','--python',getattr(sys,'_base_executable',sys.executable),target],stdout=sys.stderr,stderr=sys.stderr)
    if result.returncode:raise RuntimeError('升级未成功；请检查 uv 错误并保留原 wheel 以便重装。')
    probe=subprocess.run([sys.executable,'-c',f'import importlib.metadata; print(importlib.metadata.version({PACKAGE!r}))'],capture_output=True,text=True,check=True)
    return {'previous_version':__version__,'installed_version':probe.stdout.strip(),'source':target,'next':'重载 MCP 或重启调用方；无需修改启动配置。'}
