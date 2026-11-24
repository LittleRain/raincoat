"""分派层：workbuddy（本地 Agent）与 DeepSeek 搜索。

只负责"把问题发出去、把原文拿回来"，不做任何判断；判断在 accept.py。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .common import extract_json

LOCAL_AGENT = shutil.which("local-agent") or str(Path.home() / ".local" / "bin" / "local-agent")
LOCAL_AGENT_BRIDGE = Path.home() / ".local" / "share" / "local-agent-mcp" / "current" / "bridge.py"
DS_SEARCH = Path.home() / ".dsh" / "skills" / "qiaomu-ds-search" / "scripts" / "ds_search.py"

# 三条抓取逻辑（官方赏 / 官方福袋 / 游戏虚拟商品）派 WorkBuddy 时统一走用户自定义模型。
# WorkBuddy 把 ~/.workbuddy/models.json 里的自定义模型在 acc-product-config-v3.json 中登记为
# `custom-local:<id>`；裸 id 传进去会撞上同名官方模型，被桥接层判为「custom route」而拒收，
# 所以这里必须带 custom-local: 前缀。仍然可以用 ACG_WORKBUDDY_MODEL 覆盖（临时换模型/回滚）。
DEFAULT_WORKBUDDY_MODEL = "custom-local:deepseek-v4.1-flash"


def workbuddy_model() -> str:
    return os.environ.get("ACG_WORKBUDDY_MODEL") or DEFAULT_WORKBUDDY_MODEL


TERMINAL = {
    "succeeded",
    "failed",
    "cancelled",
    "canceled",
    "timeout",
    # 桥接层在 job 起步就死时写的是 interrupted；它不在终态里会让脚本空等满 28 分钟
    "interrupted",
    "error",
    "stopped",
    "lost",
}

# 一个 workbuddy job 最多装几个盘。19 盘塞一个 job 时模型每题只答一半
# （赏名回来了、每箱个数全空），2026-11-23 实测；排障文档的结论也是每批 ≤6。
LANE_CHUNK_SIZE = 6
# 同时跑几个 job：每个 job 是一个 Electron 进程，本机实测 3 个是稳态，再多互相拖慢。
LANE_MAX_JOBS = 3
# 提交失败 / job 起步即死时的重试次数（每个 job 一次）。
LANE_RETRY = 1

WORKBUDDY_PROFILES = ("desktop", "web")


def chunk(items: list, size: int = LANE_CHUNK_SIZE) -> list[list]:
    """把一批盘切成 ≤size 的块；size 非法时按 1 处理，保证不会退回「一坨全塞一个 job」。"""
    try:
        step = int(size or LANE_CHUNK_SIZE)
    except (TypeError, ValueError):
        step = LANE_CHUNK_SIZE
    step = max(1, step)
    rows = list(items or [])
    return [rows[index:index + step] for index in range(0, len(rows), step)]


def job_error(state: dict) -> str:
    """job 终态里的错误原文；跑成功了就是空串。"""
    return str((state or {}).get("error") or "").strip()[:300]


def _credential_helper() -> str:
    """复刻 workbuddy.mjs 的凭证 helper 解析：$WORKBUDDY_CREDENTIAL_HELPER 或 profile 里的 host-heartbeat-*.js。"""
    override = (os.environ.get("WORKBUDDY_CREDENTIAL_HELPER") or "").strip()
    if override:
        return override
    root = Path.home() / ".dsh" / "profiles"
    for profile in WORKBUDDY_PROFILES:
        lib = root / profile / "node_modules" / "dsh-workbuddy-connect" / "lib"
        try:
            matches = sorted(path for path in lib.iterdir() if re.match(r"^host-heartbeat-.*\.js$", path.name))
        except OSError:
            continue
        if len(matches) == 1:
            return str(matches[0])
    return ""


def ensure_local_agent() -> dict:
    """CLI 包装脚本被删时按已安装的 bridge 复原（2026-11-23 09:40 那次就是被删了）。

    只复原这一层 `#!/bin/sh` 包装，不重装 bridge；bridge 也不在就直接报错，让人去重装。
    """
    cli = Path(LOCAL_AGENT)
    if cli.exists() and os.access(cli, os.X_OK):
        return {"ok": True, "repaired": False, "error": ""}
    bridge = Path(LOCAL_AGENT_BRIDGE)
    if not bridge.exists():
        return {"ok": False, "repaired": False, "error": f"bridge_missing:{bridge}"}
    try:
        cli.parent.mkdir(parents=True, exist_ok=True)
        cli.write_text(f'#!/bin/sh\nexec {sys.executable} {bridge} "$@"\n', encoding="utf-8")
        cli.chmod(0o755)
    except OSError as error:
        return {"ok": False, "repaired": False, "error": f"repair_failed:{error.__class__.__name__}"}
    return {"ok": True, "repaired": True, "error": ""}


def preflight_workbuddy(timeout: int = 45) -> dict:
    """派发前自检：CLI 在不在、凭证 helper 有没有、后端 ready 没 ready。返回 {ok, error, detail}。

    2026-11-23 那轮的两个坑都是「提交时才发现」：CLI 被删 → 整轮 failed；
    credential helper 缺失 → job 起步就 interrupted，脚本干等 28 分钟。能提前查的全查完。
    """
    repair = ensure_local_agent()
    cli = Path(LOCAL_AGENT)
    if not repair["ok"] or not (cli.exists() and os.access(cli, os.X_OK)):
        return {"ok": False, "error": f"local_agent_missing:{cli}（{repair['error']}）", "detail": {}}
    helper = _credential_helper()
    if not helper:
        return {
            "ok": False,
            "error": "credential_helper_missing:dsh-workbuddy-connect（重装插件或设置 WORKBUDDY_CREDENTIAL_HELPER）",
            "detail": {"profiles": list(WORKBUDDY_PROFILES), "repaired": repair["repaired"]},
        }
    try:
        result = subprocess.run(
            [str(cli), "status", "workbuddy"], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "status_timeout", "detail": {"helper": helper}}
    except OSError as error:
        return {"ok": False, "error": f"status_oserror:{error.__class__.__name__}", "detail": {"helper": helper}}
    if result.returncode != 0:
        return {
            "ok": False,
            "error": f"status_exit_{result.returncode}:{(result.stderr or result.stdout).strip()[:200]}",
            "detail": {"helper": helper},
        }
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "status_bad_json", "detail": {"helper": helper}}
    detail = {
        "installed": bool(payload.get("installed")),
        "executionReady": bool(payload.get("execution_ready")),
        "helper": helper,
        "repaired": repair["repaired"],
    }
    if not detail["installed"]:
        return {"ok": False, "error": "workbuddy_not_installed", "detail": detail}
    if not detail["executionReady"]:
        return {"ok": False, "error": "workbuddy_not_execution_ready", "detail": detail}
    return {"ok": True, "error": "", "detail": detail}


def preflight_deepseek() -> dict:
    """DeepSeek 通道前置检查：脚本在不在、有没有 API Key（没有就是全盘失败，不必等 3 分钟）。"""
    if not DS_SEARCH.exists():
        return {"ok": False, "error": f"ds_search_missing:{DS_SEARCH}", "detail": {}}
    if os.environ.get("DEEPSEEK_API_KEY", "").strip():
        return {"ok": True, "error": "", "detail": {"key": "env"}}
    config = Path.home() / ".config" / "qiaomu-ds-search" / "credentials.json"
    try:
        payload = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "error": "ds_api_key_missing", "detail": {"config": str(config)}}
    if not str(payload.get("api_key") or "").strip():
        return {"ok": False, "error": "ds_api_key_missing", "detail": {"config": str(config)}}
    return {"ok": True, "error": "", "detail": {"key": "config"}}


def _read_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def submit_workbuddy(prompt: str, title: str, workdir: Path, model: str | None = None) -> dict:
    # CLI 被删过（2026-11-23 09:40）：异常要在派发这一层就说清，而不是丢一个 Errno 2 上去
    if not (Path(LOCAL_AGENT).exists() and os.access(LOCAL_AGENT, os.X_OK)):
        raise RuntimeError(f"local_agent_missing:{LOCAL_AGENT}（重新安装 local-agent 后再跑）")
    workdir.mkdir(parents=True, exist_ok=True)
    prompt_file = workdir / f"{title}.prompt.txt"
    prompt_file.write_text(prompt, encoding="utf-8")
    resolved_model = model or workbuddy_model()
    command = [
        LOCAL_AGENT,
        "submit",
        "workbuddy",
        "--prompt-file",
        str(prompt_file),
        "--title",
        title,
        "--model",
        resolved_model,
        "--allowed-tool",
        "WebSearch",
        "--allowed-tool",
        "WebFetch",
        "--wait-seconds",
        "1",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"submit 失败: {(result.stderr or result.stdout)[:300]}")
    payload = json.loads(result.stdout)
    return {
        "jobId": payload.get("job_id"),
        "status": payload.get("status"),
        "model": resolved_model,
        "resultPath": payload.get("result_path"),
        "statePath": payload.get("result_path"),
    }


def wait_job(result_path: str, timeout: int = 600, interval: int = 5, on_tick=None) -> dict:
    """轮询 job state；返回终态快照。"""
    path = Path(result_path)
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = _read_state(path)
        status = (last.get("status") or "").lower()
        if on_tick:
            on_tick(last, status)
        if status in TERMINAL:
            last["_elapsed"] = int(timeout - (deadline - time.time()))
            return last
        time.sleep(interval)
    last = last or {}
    last["status"] = "timeout"
    last["_elapsed"] = timeout
    return last


def cancel_job(job_id: str, timeout: int = 30) -> dict:
    """取消一个还在跑的 workbuddy job。

    整轮预算用尽时用：等到点的 job 已经拿不到有效输出，继续跑只会烧 token。
    """
    if not job_id:
        return {"ok": False, "error": "missing_job_id"}
    try:
        result = subprocess.run(
            [LOCAL_AGENT, "cancel", str(job_id)], capture_output=True, text=True, timeout=timeout
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        return {"ok": False, "error": error.__class__.__name__}
    if result.returncode != 0:
        return {"ok": False, "error": (result.stderr or result.stdout or "")[:200]}
    return {"ok": True, "error": ""}


def parse_candidates(text: str) -> list[dict]:
    value = extract_json(text or "")
    if value is None:
        return []
    if isinstance(value, dict):
        for key in ("pans", "items", "results", "data"):
            if isinstance(value.get(key), list):
                return [x for x in value[key] if isinstance(x, dict)]
        if "pan" in value or "name" in value:
            return [value]
        return []
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return []


_PIPE_SPLIT = re.compile(r"\s*[|｜]\s*")
_PRICE_RE = re.compile(r"(?:￥|¥|RMB\s*)?(\d{2,5})\s*元")
_URL_RE = re.compile(r"https?://[^\s|｜)）]+")
_TEXT_CARRIERS = ("福袋", "惊喜福袋", "神秘盒子", "礼盒", "惊喜袋", "盲袋", "礼包")
_HEADER_WORDS = {"商品名称", "名称", "商品", "内容", "IP", "ip", "说明", "备注"}


def _text_candidate(cells: list[str]) -> dict | None:
    """「商品名称 | 内容 | IP」三列 → 候选。内容里的价格/链接顺手抠出来。"""
    cells = [cell.strip() for cell in cells if cell.strip()]
    if len(cells) < 2:
        return None
    name, content = cells[0], cells[1]
    ip = cells[2] if len(cells) > 2 else ""
    if not name or name.strip("-*+ ") in _HEADER_WORDS:
        return None
    haystack = f"{name}{content}"
    carrier = next((word for word in _TEXT_CARRIERS if word in haystack), "")
    price_match = _PRICE_RE.search(content)
    url_match = _URL_RE.search(content)
    tiers = []
    if price_match:
        tiers.append(
            {
                "price": int(price_match.group(1)),
                "items": "",
                "quote": content,
                "source": url_match.group(0) if url_match else "",
            }
        )
    return {
        "ip": ip,
        "officialName": name,
        "carrier": carrier,
        "tiers": tiers,
        "source": url_match.group(0) if url_match else "",
        "quote": content,
        "window": {},
    }


def parse_text_candidates(text: str) -> list[dict]:
    """兜底解析：agent 没按 JSON 返回时，读「商品名称 | 内容 | IP」这种一行一条的写法。

    支持 markdown 表格（含表头/分隔行）和普通竖线行；解析不出就返回 []，
    宁可少收也不要塞垃圾进验收。
    """
    rows: list[dict] = []
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("-*+").strip()
        if not line or "|" not in line and "｜" not in line:
            continue
        cells = [cell.strip() for cell in _PIPE_SPLIT.split(line) if cell.strip()]
        if len(cells) < 2 or all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        candidate = _text_candidate(cells)
        if candidate:
            rows.append(candidate)
    return rows


def ds_search(query: str, count: int = 5, timeout: int = 60) -> dict:
    """调 DeepSeek 官方 Search API，返回结构化结果（公众号渠道靠它找文章页）。"""
    if not DS_SEARCH.exists():
        return {"ok": False, "error": "ds_search_missing", "results": []}
    try:
        result = subprocess.run(
            ["python3", str(DS_SEARCH), "search", query, "--count", str(count)],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "results": []}
    except OSError as error:
        return {"ok": False, "error": f"{error.__class__.__name__}", "results": []}
    if result.returncode != 0:
        return {"ok": False, "error": (result.stderr or result.stdout)[:200], "results": []}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "bad_json", "results": []}
    if not isinstance(payload, dict) or not payload.get("ok"):
        return {"ok": False, "error": str((payload or {}).get("error") or "api_error"), "results": []}
    return {"ok": True, "error": "", "results": payload.get("results") or []}


def run_ds_query(query: str, timeout: int = 120) -> dict:
    """DeepSeek 搜索：返回原文文本，供验收层抽取；失败不抛。"""
    if not DS_SEARCH.exists():
        return {"ok": False, "error": "ds_search_missing", "text": ""}
    try:
        result = subprocess.run(
            ["python3", str(DS_SEARCH), "search", query, "--count", "5"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return {"ok": False, "error": (result.stderr or "")[:200], "text": ""}
        return {"ok": True, "error": "", "text": result.stdout}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "text": ""}


def wait_jobs(result_paths: list[str], timeout: int = 1200, interval: int = 5, on_tick=None) -> list[dict]:
    """同时轮询多个 job：谁先到终态谁先算，到点还没完的标 timeout（结果可 --resume 回收）。"""
    deadline = time.time() + timeout
    last: dict[str, dict] = {path: {} for path in result_paths}
    while time.time() < deadline:
        running = 0
        for path in result_paths:
            state = _read_state(Path(path))
            if state:
                last[path] = state
            if (state.get("status") or "").lower() not in TERMINAL:
                running += 1
        if on_tick:
            on_tick(last, running)
        if running == 0:
            break
        time.sleep(interval)

    finished = []
    for path in result_paths:
        snapshot = dict(last.get(path) or {})
        if (snapshot.get("status") or "").lower() not in TERMINAL:
            snapshot["status"] = "timeout"
        finished.append(snapshot)
    return finished


def fetch_job(job_id: str, timeout: int = 90) -> dict:
    """按 job_id 取终态（--resume 用）：超时放弃后 Agent 可能还在跑，跑完了就能把结果捞回来。"""
    if not job_id:
        return {"status": "missing", "text": "", "error": "no_job_id"}
    try:
        result = subprocess.run(
            [LOCAL_AGENT, "get", job_id], capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"status": "unreachable", "text": "", "error": str(error)}
    if result.returncode != 0:
        return {"status": "unreachable", "text": "", "error": (result.stderr or result.stdout)[:300]}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "unreachable", "text": "", "error": "bad_payload"}
    if not isinstance(payload, dict):
        return {"status": "unreachable", "text": "", "error": "bad_payload"}
    return payload
