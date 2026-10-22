"""WorkBuddy discovery only; persistent credential adapter awaits authorization."""
from pathlib import Path

APP = Path('/Applications/WorkBuddy.app')
AUTHORIZATION_PENDING = 'WorkBuddy 正式后端尚未启用：持续复用桌面登录凭证向运行时认证的授权待确认。'


def status():
    return {'installed': APP.is_dir(), 'runtime': 'WorkBuddy bundled Agent CLI',
            'execution_ready': False, 'desktop_task_visible': False,
            'note': AUTHORIZATION_PENDING}


async def run(ctx):
    raise RuntimeError(AUTHORIZATION_PENDING)
