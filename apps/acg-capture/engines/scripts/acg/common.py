"""ACG 官方赏抓取：公共工具。

设计约束（和方案对齐）：
- 企微表格是唯一真源，外部信息只是候选；本模块只提供读写与校验的原子能力。
- 运行事件走 stdout（`@@ACG@@ {json}`）+ run 目录 events.jsonl，插件按前缀解析。
- 所有外网请求默认绕开本机失效代理；二手平台域名在验收层硬拒。
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:  # POSIX 用 flock；Windows 上退化成进程内无锁（本工作流的运行时都在 macOS）
    import fcntl
except ImportError:  # pragma: no cover - 只在非 POSIX 平台触发
    fcntl = None

# ---------------------------------------------------------------- 并发写

@contextlib.contextmanager
def run_lock(run_dir: Path):
    """同一 run 的裁决串行化（跨进程）。

    插件里同时点多个「采信」，每个点击都会 spawn 一个 python 进程去读改写 run.json。
    没有锁时两个进程都读到「A、B 都还是待确认」，各自把自己那条改成已采信再整体覆盖，
    后写的会把先写的状态顶回 pending_review —— 界面上看就是「只有一条成功」。
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    if fcntl is None:  # pragma: no cover
        yield
        return
    with open(run_dir / ".decide.lock", "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def save_state(state_path: Path, state: dict) -> None:
    """原子落盘：先写临时文件再 replace，避免并发读到一个写了一半的 run.json。

    临时文件名带 pid：即便有调用方绕过 run_lock，也不会两个进程抢同一个 .tmp 互相 replace 掉。
    """
    state_path = Path(state_path)
    tmp = state_path.with_name(f"{state_path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, state_path)


# ---------------------------------------------------------------- 路径

# 应用内引擎根：apps/acg-capture/engines（原 workspace 的 workflows/kuji-tracking）
WORKFLOW = Path(__file__).resolve().parents[2]
ROOT = WORKFLOW.parent
DATA_DIR = Path(os.environ.get("ACG_DATA_DIR") or (Path.home() / ".dsh" / "acg-capture"))
RUNS_DIR = DATA_DIR / "runs"
LOCKS_DIR = DATA_DIR / "locks"
CACHE_DIR = DATA_DIR / "cache"
CHANNELS_FILE = WORKFLOW / "references" / "channels.json"
BAG_LEADS_FILE = WORKFLOW / "references" / "bag-leads.json"
BAG_CHANNELS_FILE = WORKFLOW / "references" / "bag-channels.json"
BAG_FIELDS_CACHE = CACHE_DIR / "bag-fields.json"
BAG_LEDGER_CACHE = CACHE_DIR / "bag-ledger.json"
# 游戏虚拟商品：没有游戏订阅库，台账（企微「游戏虚拟商品」子表）就是游戏清单
VG_SOURCES_FILE = WORKFLOW / "references" / "vg-sources.json"
VG_FIELDS_CACHE = CACHE_DIR / "vg-fields.json"
VG_LEDGER_CACHE = CACHE_DIR / "vg-ledger.json"

TZ = timezone(timedelta(hours=8))

# 企微「官方抽赏类商品追踪」
DOC_URL = (
    "https://doc.weixin.qq.com/smartsheet/s3_Af0A3AZAAEcCNLf1EXDRzSXK0El6U"
    "?scode=ANYAEAdoABENoTELTOAf0A3AZAAEc&tab=tmNNY2&viewId=viVT9X"
)
SHEET_PAN = "tmNNY2"
SHEET_SUB = "tKst6t"
# 企微「官方福袋」子表（同一份智能表格）
SHEET_BAG = "tvZwq0"
# 企微「游戏虚拟商品」子表（同一份智能表格）
SHEET_VG = "ty2XMk"

# 二手 / 非官方来源：只允许当线索，数字一律不采
SECONDHAND_HOSTS = (
    "qiandao",
    "goofish",
    "xianyu",
    "2.taobao",
    "douyin",
    "kujihunter",
    "kujimap",
)


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- 文本

def txt(value) -> str:
    """企微文本单元格：list[{text}] / {text} / 标量，统一成字符串。"""
    if value is None:
        return ""
    if isinstance(value, list):
        return "".join(x.get("text", "") for x in value if isinstance(x, dict))
    if isinstance(value, dict):
        return value.get("text", "") or ""
    return str(value)


def num(value):
    """数字单元格 → int；空/非数字返回 None。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = txt(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def norm(value: str) -> str:
    """名称归一化：全半角、空白、大小写、常见括号差异。"""
    text = unicodedata.normalize("NFKC", value or "").lower()
    text = re.sub(r"[\s\u3000]+", "", text)
    text = text.replace("（", "(").replace("）", ")")
    return text


def cell_text(value: str) -> str:
    """写入企微文本单元格的格式。"""
    return json.dumps([{"text": value, "type": "text"}], ensure_ascii=False)


def host_of(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def is_secondhand(url: str) -> bool:
    host = host_of(url)
    return any(bad in host for bad in SECONDHAND_HOSTS)


# ---------------------------------------------------------------- JSON

def extract_json(text: str):
    """从 Agent 输出里抠出第一个 JSON 值（容忍 ```json 围栏和前后说明）。"""
    if not text:
        return None
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", cleaned, re.S)
    if fenced:
        cleaned = fenced.group(1).strip()
    starts = [i for i in (cleaned.find("["), cleaned.find("{")) if i >= 0]
    if not starts:
        return None
    start = min(starts)
    decoder = json.JSONDecoder()
    try:
        value, _ = decoder.raw_decode(cleaned[start:])
        return value
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------- HTTP

def _opener():
    # 本机代理已失效：显式禁用，避免境外站全部超时
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch_text(url: str, timeout: int = 15, retries: int = 1) -> tuple[bool, str, str]:
    """返回 (ok, text, error)。只取前 400KB，够做原文校验。"""
    if not url or not url.startswith("http"):
        return False, "", "invalid_url"
    request = urllib.request.Request(
        url,
        headers={
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
            ),
            "accept-language": "zh-CN,zh;q=0.9,ja;q=0.8",
        },
    )
    last_error = ""
    for _ in range(max(1, retries)):
        try:
            with _opener().open(request, timeout=timeout) as response:
                raw = response.read(400_000)
                charset = response.headers.get_content_charset() or "utf-8"
                return True, raw.decode(charset, "ignore"), ""
        except urllib.error.HTTPError as error:
            last_error = f"http_{error.code}"
        except Exception as error:  # noqa: BLE001 - 网络异常一律降级
            last_error = error.__class__.__name__
    return False, "", last_error


def fuzzy_contains(page: str, text: str, threshold: float = 0.6) -> bool:
    """逐字对不上时的兜底：按 2-gram 覆盖率判断（小红书/微博正文常带表情、换行、简称）。

    只放宽「措辞」，不放宽「数字」——调用方拿到 True 后仍然要自己核对数字。
    """
    if not page or not text:
        return False
    hay = unicodedata.normalize("NFKC", re.sub(r"<[^>]+>", " ", page))
    hay = re.sub(r"[\s\u3000]+", "", hay)
    needle = unicodedata.normalize("NFKC", str(text))
    needle = re.sub(r"[\s\u3000]+", "", needle)
    if len(needle) < 4:
        return False
    if needle in hay:
        return True
    grams = [needle[i : i + 2] for i in range(len(needle) - 1)]
    hit = sum(1 for gram in grams if gram in hay)
    return hit / max(1, len(grams)) >= threshold


def page_contains(page: str, quote: str) -> bool:
    """原文命中：去标签、空白与全半角后再比。"""
    if not quote:
        return False
    text = re.sub(r"<[^>]+>", " ", page)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\s\u3000]+", "", text)
    target = unicodedata.normalize("NFKC", quote)
    target = re.sub(r"[\s\u3000]+", "", target)
    return target in text


# ---------------------------------------------------------------- 企微 CLI

def _cli_env() -> dict:
    env = dict(os.environ)
    extra = [str(Path.home() / ".local" / "bin")]
    for candidate in Path("/Users").glob(r"*/.nvm/versions/node/*/bin"):
        extra.append(str(candidate))
    env["PATH"] = ":".join([*extra, env.get("PATH", "")])
    return env


def wecom_bin() -> str:
    found = shutil.which("wecom-cli", path=_cli_env()["PATH"])
    if not found:
        raise RuntimeError("wecom-cli 不在 PATH 上")
    return found


def run_wecom(args: list[str], timeout: int = 120) -> dict:
    """调用 wecom-cli，stdout 可能是日志，因此统一用 -o 落临时文件再读。"""
    # wecom-cli 的 -o 不覆盖已存在文件：拿一个不存在的路径，别预先建文件
    out_path = Path(tempfile.mkdtemp(prefix="acg-wecom-")) / "out.json"
    try:
        command = [wecom_bin(), *args, "-o", str(out_path)]
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, env=_cli_env()
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"wecom-cli 退出码 {result.returncode}: {(result.stderr or result.stdout)[:400]}"
            )
        raw = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
        if not raw.strip():
            raise RuntimeError("wecom-cli 没有产出内容")
        return json.loads(raw)
    finally:
        out_path.unlink(missing_ok=True)
        try:
            out_path.parent.rmdir()
        except OSError:
            pass


def pull_sheet(sheet_id: str, limit: int = 1000) -> list[dict]:
    """分页拉全表：返回合并后的 records。"""
    records: list[dict] = []
    start = 0
    while True:
        payload = run_wecom(
            [
                "smartsheet",
                "records",
                "list",
                "--docid",
                DOC_URL,
                "--sheet-id",
                sheet_id,
                "--type",
                "records",
                "--limit",
                str(limit),
                "--start",
                str(start),
            ]
        )
        page = payload.get("records") or []
        records.extend(page)
        if len(page) < limit:
            break
        start += limit
        if start > 20_000:
            break
    return records


# ---------------------------------------------------------------- 运行存储

class Run:
    """一次抓取运行：run.json + events.jsonl，插件只读这两份。"""

    def __init__(self, kind: str, trigger: str = "manual", dry_run: bool = True, params=None, run_id: str | None = None):
        stamp = datetime.now(TZ).strftime("%Y%m%d-%H%M%S")
        self.id = run_id or f"r-{stamp}-{kind}"
        self.dir = RUNS_DIR / self.id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state = {
            "id": self.id,
            "kind": kind,
            "trigger": trigger,
            "dryRun": bool(dry_run),
            "startedAt": now_iso(),
            "endedAt": None,
            "status": "running",
            "stage": "preparing",
            "pid": os.getpid(),
            "params": params or {},
            "table": {},
            "counts": {
                "dispatched": 0,
                "done": 0,
                "accepted": 0,
                "rejected": 0,
                "pending": 0,
                # 来源未公布（没有可确认内容）：和待确认分开算，不占人工裁决队列
                "unavailable": 0,
                "written": 0,
            },
            "items": [],
            "error": None,
        }
        self._seq = 0
        self._events = (self.dir / "events.jsonl").open("a", encoding="utf-8")
        self.save()

    # -- 事件 ---------------------------------------------------------
    def event(self, event_type: str, **data):
        self._seq += 1
        payload = {"seq": self._seq, "at": now_iso(), "type": event_type, **data}
        self._events.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._events.flush()
        print("@@ACG@@ " + json.dumps(payload, ensure_ascii=False), flush=True)

    def stage(self, name: str, **extra):
        self.state["stage"] = name
        self.save()
        self.event("stage", stage=name, **extra)

    def set_table(self, **info):
        self.state["table"].update(info)
        self.save()

    def set_count(self, key: str, value: int):
        self.state["counts"][key] = int(value)
        self.save()

    def bump(self, key: str, delta: int = 1):
        self.set_count(key, self.state["counts"].get(key, 0) + delta)

    def add_item(self, item: dict) -> dict:
        item.setdefault("id", f"i-{len(self.state['items']) + 1}")
        self.state["items"].append(item)
        self.save()
        self.event("item", item=item)
        return item

    def finish(self, status: str = "done", error: str | None = None):
        self.state["status"] = status
        if status == "done":
            self.state["stage"] = "done"
        self.state["endedAt"] = now_iso()
        self.state["error"] = error
        self.save()
        self.event("end", status=status, error=error, counts=self.state["counts"])
        self._events.close()

    def save(self):
        tmp = self.dir / "run.json.tmp"
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.dir / "run.json")


def latest_run(kind: str | None = None) -> dict | None:
    if not RUNS_DIR.exists():
        return None
    candidates = sorted(RUNS_DIR.glob("r-*"), reverse=True)
    for path in candidates:
        run_json = path / "run.json"
        if not run_json.exists():
            continue
        try:
            data = json.loads(run_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if kind and data.get("kind") != kind:
            continue
        return data
    return None


def last_success_date(kind: str) -> str | None:
    """最近一次成功运行的日期，抓新品用它算窗口。

    只有「Agent 真的回答过」的运行才推进窗口锚点：
    2026-11-17 那次 Agent 超时、0 结果的运行被记成 done，锚点跟着前移，
    15 号那天的窗口就再也不会被扫——这里改成按 answer 判定。
    """
    if not RUNS_DIR.exists():
        return None
    for path in sorted(RUNS_DIR.glob("r-*"), reverse=True):
        run_json = path / "run.json"
        if not run_json.exists():
            continue
        try:
            data = json.loads(run_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("kind") != kind:
            continue
        if data.get("status") not in ("done", "partial"):
            continue
        answer = data.get("answer") or {}
        groups = int(answer.get("groups") or 0)
        answered = int(answer.get("answered") or 0)
        if groups and answered < groups:
            continue
        if not groups and not (data.get("counts") or {}).get("accepted"):
            # 老格式没有 answer：只有真的写进表才算成功，空跑不推进
            continue
        started = (data.get("startedAt") or "")[:10]
        if started:
            return started
        return path.name[2:10]
    return None
