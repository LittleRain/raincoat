"""官方福袋抓取运行：按线索派发双源 → 合并 → 验收 → 写企微「官方福袋」表 → 回写线索。"""

from __future__ import annotations

import concurrent.futures as futures
import json
import os
import time
from datetime import datetime, timedelta

from . import bag_accept, bag_channels, bag_dispatch, bag_leads, bag_table, dispatch

# 任务切块：不按发行方分（一个 job 里可以有腾讯、米哈游、网易混着），
# 就按线索表顺序每 N 条一块，一块一个 job。
# 68 条线索按 10 条一块 → 7 个 sweep job；条数调小 → job 更多更细，调大 → 更省但单 job 更久。
SWEEP_LEADS_PER_JOB = int(os.environ.get("ACG_SWEEP_MAX_LEADS_PER_JOB") or 5)
# 定向任务单独切：只覆盖有 confirmed 渠道的线索，单 job 别背太多（要逐页翻渠道）
CHANNEL_LEADS_PER_JOB = int(os.environ.get("ACG_CHANNEL_MAX_LEADS_PER_JOB") or 3)
# 同时活着的 workbuddy job 上限：submit 即开跑。默认 40 ≈ 不封顶（26 个 job 一起起跑），
# 整轮时长由最慢那个 job 决定；真正的硬约束是下面的 RUN_BUDGET_SECONDS。
MAX_INFLIGHT_JOBS = int(os.environ.get("ACG_MAX_WB_JOBS") or 40)
# DeepSeek 单线索抽取的并发数（与 workbuddy 同时跑，最后统一合并）。
DS_WORKERS = int(os.environ.get("ACG_DS_WORKERS") or 4)

# 单 job 等待上限：默认按「线索数」算，而不是一个固定值 —— 组数少的时候单 job 背得多，
# 固定 1200 秒会把尾巴上的 IP 直接砍掉。自定义模型（custom-local:deepseek-v4.1-flash）比原 deep-model
# 更爱多搜几页：2026-11-18 实测 420 秒必然截断、3 条/job 曾顶满 1200 秒，所以每条线索留 180 秒。
WB_WAIT_FIXED = int(os.environ.get("ACG_WB_WAIT_SECONDS") or 0)  # 显式给了就照办（调试/冒烟用）
WB_WAIT_PER_LEAD = int(os.environ.get("ACG_WB_WAIT_PER_LEAD") or 180)
WB_WAIT_SLACK = int(os.environ.get("ACG_WB_WAIT_SLACK") or 600)
WB_WAIT_MAX = int(os.environ.get("ACG_WB_WAIT_MAX") or 3600)

# 整轮硬预算：到点就收工。用户要求「一轮不超过半小时」，光限单 job 不够 ——
# 26 个 job 里只要有一个慢，总时长就会跟着它走。到预算后不再派新 job，
# 在跑的按剩余时间等，到点取消（local-agent cancel），已拿到的候选照常合并验收。
# 默认 25 分钟派发+采集，再留 5 分钟给验收/写表 → 整轮压在 30 分钟内。
RUN_BUDGET_SECONDS = int(os.environ.get("ACG_RUN_BUDGET_SECONDS") or 1500)
# 末段留多少给合并 / 验收 / 写表（验收要逐条抓页面，不能挤在最后一秒）
BUDGET_RESERVE = int(os.environ.get("ACG_RUN_BUDGET_RESERVE") or 300)
DS_LEAD_TIMEOUT = int(os.environ.get("ACG_DS_LEAD_TIMEOUT") or 300)


def _job_timeout(lead_count: int, remaining: float | None = None) -> int:
    """单 job 等多久：固定值优先，否则 600 秒起手 + 每条线索 180 秒，封顶 3600 秒。

    给了 remaining（整轮还剩多少秒）就再压一刀，保证不会把预算吃穿。
    """
    if WB_WAIT_FIXED:
        return WB_WAIT_FIXED  # 显式指定（调试/冒烟）就不裁剪，按用户给的值等
    base = max(300, min(WB_WAIT_MAX, WB_WAIT_SLACK + WB_WAIT_PER_LEAD * max(1, lead_count)))
    if remaining is None:
        return base
    return max(30, int(min(base, remaining - BUDGET_RESERVE)))


def _remaining(deadline: float | None) -> float:
    return float("inf") if deadline is None else deadline - time.monotonic()
from .common import RUNS_DIR, TZ, Run, norm, now_iso, today


def _last_write_date() -> str | None:
    """最近一次「写表」成功的日期；dry-run 不算，避免空跑推进窗口。"""
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
        if data.get("kind") != "bag-discover" or data.get("dryRun") or data.get("status") != "done":
            continue
        return (data.get("startedAt") or "")[:10] or None
    return None


def _window(since: str, until: str) -> tuple[str, str]:
    until = until or today()
    if since:
        return since, until
    anchor = _last_write_date()
    if anchor:
        base = datetime.strptime(anchor, "%Y-%m-%d")
        return (base - timedelta(days=1)).strftime("%Y-%m-%d"), until
    base = datetime.now(TZ) - timedelta(days=60)
    return base.strftime("%Y-%m-%d"), until


def _select(leads: list[dict], wanted: str) -> list[dict]:
    if wanted:
        ids = {x.strip() for x in wanted.split(",") if x.strip()}
        return [lead for lead in leads if lead.get("id") in ids]
    return [lead for lead in leads if lead.get("status") == "active"]


def _chunks(leads: list[dict], size: int) -> list[list[dict]]:
    """按顺序每 size 条切一块 —— 不分发行方，一个 job 里可以是不同发行方的 IP。"""
    size = max(1, int(size))
    return [leads[index:index + size] for index in range(0, len(leads), size)]


def _chunk_label(group: list[dict]) -> str:
    ips = [str(lead.get("ip") or "") for lead in group if lead.get("ip")]
    if not ips:
        return "未命名"
    head = "、".join(ips[:2])
    return head if len(ips) <= 2 else f"{head} 等 {len(ips)} 个"


def _lead_channel_ids(leads: list[dict]) -> set[str]:
    return {cid for lead in leads for cid in (lead.get("channelIds") or [])}


def _plan_jobs(
    leads: list[dict],
    channels: dict[str, dict],
    usable_ids: set[str],
    since: str,
    until: str,
    modes: set[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """把这一轮要派的 workbuddy 任务算出来（纯函数，离线可测）。

    两套任务：
      - sweep：所有激活线索按顺序每 SWEEP_LEADS_PER_JOB 条一块，一块一个 job，全网扫；
      - channel：只挑绑了可用渠道的线索，单独切块，逐页翻那些 confirmed 渠道。
    不按发行方分组：一个 job 里混着不同发行方是正常的。
    返回 (sweep_jobs, channel_jobs)，每项含 mode/label/leads/channelIds/prompt。
    """
    wanted = modes or {"sweep", "channel"}

    sweep_jobs: list[dict] = []
    if "sweep" in wanted:
        for group in _chunks(leads, SWEEP_LEADS_PER_JOB):
            sweep_jobs.append(
                {
                    "mode": "sweep",
                    "label": _chunk_label(group),
                    "leads": group,
                    "channelIds": [],
                    "prompt": bag_dispatch.sweep_prompt(group, since, until),
                }
            )

    channel_jobs: list[dict] = []
    if "channel" in wanted:
        targeted = [lead for lead in leads if _lead_channel_ids([lead]) & usable_ids]
        for group in _chunks(targeted, CHANNEL_LEADS_PER_JOB):
            used = [channels[cid] for cid in sorted(_lead_channel_ids(group)) if cid in usable_ids]
            if not used:
                continue
            channel_jobs.append(
                {
                    "mode": "channel",
                    "label": _chunk_label(group),
                    "leads": group,
                    "channelIds": [row["id"] for row in used],
                    "prompt": bag_dispatch.workbuddy_prompt(_chunk_label(group), group, used, since, until),
                }
            )
    return sweep_jobs, channel_jobs


def run(
    leads_filter: str = "",
    lanes: str = "workbuddy,deepseek",
    since: str = "",
    until: str = "",
    write: bool = True,
    use_agent: bool = True,
    run_id: str | None = None,
    trigger: str = "manual",
    modes: str = "",
) -> Run:
    lead_data = bag_leads.load()
    channel_rows = bag_channels.load()["channels"]
    channels = {row["id"]: row for row in channel_rows}
    selected = _select(lead_data["leads"], leads_filter)
    since, until = _window(since, until)
    lane_set = {x.strip() for x in lanes.split(",") if x.strip()} & {"workbuddy", "deepseek"}
    mode_set = {x.strip() for x in modes.split(",") if x.strip()} & {"sweep", "channel"} or {"sweep", "channel"}
    if not use_agent:
        lane_set = set()

    run = Run("bag-discover", trigger=trigger, dry_run=not write, run_id=run_id)
    run.state["params"].update(
        {
            "since": since,
            "until": until,
            "lanes": sorted(lane_set),
            "modes": sorted(mode_set),
            "leads": [lead["id"] for lead in selected],
        }
    )
    run.set_table(leads=len(lead_data["leads"]), selected=len(selected), channels=len(channel_rows))
    run.event("window", since=since, until=until, leads=len(selected), lanes=sorted(lane_set))
    if not selected:
        run.finish("failed", "没有可跑的线索（全部暂停或被过滤）")
        return run

    usable = [row for row in channel_rows if bag_channels.usable(row)]
    usable_ids = {row["id"] for row in usable}
    run.event("channels", usable=len(usable), total=len(channel_rows))

    # ---- 派发 --------------------------------------------------------
    run.stage("dispatch")
    groups: dict[str, list[dict]] = {}
    for lead in selected:
        groups.setdefault(lead.get("publisher") or "未知发行方", []).append(lead)

    if "workbuddy" in lane_set:
        sweep_jobs, channel_jobs = _plan_jobs(selected, channels, usable_ids, since, until, mode_set)
    else:
        sweep_jobs, channel_jobs = [], []
    job_specs = sweep_jobs + channel_jobs
    for spec in job_specs:
        spec["title"] = f"bag-{spec['mode']}-{bag_accept._slug(spec['label'], 16)}-{run.id[-6:]}"

    def _ips(specs: list[dict]) -> list[str]:
        seen: list[str] = []
        for spec in specs:
            for lead in spec["leads"]:
                if lead["ip"] not in seen:
                    seen.append(lead["ip"])
        return seen

    run.state["scope"] = {
        "window": {"since": since, "until": until},
        "lanes": sorted(lane_set),
        "leads": [
            {"id": lead["id"], "ip": lead.get("ip"), "publisher": lead.get("publisher"), "priority": lead.get("priority")}
            for lead in selected
        ],
        "publishers": {publisher: len(group) for publisher, group in groups.items()},
        "groups": [
            {"name": f"g{index}", "publisher": publisher, "leads": [lead.get("ip") for lead in group]}
            for index, (publisher, group) in enumerate(groups.items(), 1)
        ],
        # 两套任务分开记：sweep 是全量扫街（覆盖全部线索），channel 是有渠道的定向补抓
        "modes": {
            "sweep": {"jobs": len(sweep_jobs), "leads": len(_ips(sweep_jobs)), "ips": _ips(sweep_jobs)},
            "channel": {"jobs": len(channel_jobs), "leads": len(_ips(channel_jobs)), "ips": _ips(channel_jobs)},
        },
        "jobs": [
            {
                "mode": spec["mode"],
                "label": spec["label"],
                "leads": [lead["ip"] for lead in spec["leads"]],
                "channelIds": spec["channelIds"],
            }
            for spec in job_specs
        ],
    }
    run.save()
    for spec in job_specs:
        run.event(
            "job_planned",
            mode=spec["mode"],
            publisher=spec["label"],
            leads=[lead["id"] for lead in spec["leads"]],
            channels=spec["channelIds"],
        )

    # ---- 等待与采集（workbuddy 边跑边收，DeepSeek 同时跑）----------------
    run.stage("waiting")
    wb_candidates: list[dict] = []
    lane_errors: list[dict] = []

    ds_candidates: list[dict] = []
    ds_pool = futures.ThreadPoolExecutor(max_workers=max(1, DS_WORKERS)) if "deepseek" in lane_set else None
    ds_futures: dict[str, futures.Future] = {}
    if ds_pool:
        # DeepSeek 一路是逐线索全网搜索，不依赖渠道，和 workbuddy 并行开跑，末尾一起合并
        for lead in selected:
            ds_futures[lead["id"]] = ds_pool.submit(bag_dispatch.ds_extract, lead, since, until)

    queue = list(job_specs)
    inflight: dict[futures.Future, dict] = {}
    pool = futures.ThreadPoolExecutor(max_workers=max(1, MAX_INFLIGHT_JOBS))
    # 整轮硬预算：从派发开始计时，到点收工（accepting 阶段的页面核对另行留给 BUDGET_RESERVE）
    started = time.monotonic()
    deadline = started + RUN_BUDGET_SECONDS if RUN_BUDGET_SECONDS > 0 else None
    skipped_budget: list[dict] = []
    cancelled: list[str] = []
    try:
        while queue or inflight:
            # 提交限流：默认 40 基本等于全并发；预算不够再开新 job 就直接收手
            while queue and len(inflight) < MAX_INFLIGHT_JOBS:
                if deadline is not None and _remaining(deadline) <= BUDGET_RESERVE:
                    for spec in queue:
                        skipped_budget.append(
                            {"mode": spec["mode"], "label": spec["label"], "leads": [lead["id"] for lead in spec["leads"]]}
                        )
                    run.event("job_skipped", reason="budget", count=len(queue))
                    queue.clear()
                    break
                spec = queue.pop(0)
                try:
                    job = bag_dispatch.submit(spec["prompt"], spec["title"], run.dir / "jobs")
                except Exception as error:  # noqa: BLE001 - 单组失败不阻断其它组
                    run.event("job_error", mode=spec["mode"], publisher=spec["label"], error=str(error)[:200])
                    lane_errors.append(
                        {
                            "lane": "workbuddy",
                            "mode": spec["mode"],
                            "id": spec["label"],
                            "leads": [lead["id"] for lead in spec["leads"]],
                            "status": "submit_failed",
                        }
                    )
                    continue
                wait_seconds = _job_timeout(len(spec["leads"]), _remaining(deadline))
                inflight[pool.submit(dispatch.wait_job, job["resultPath"], wait_seconds, 5)] = {
                    **spec,
                    "job": job,
                    "waitSeconds": wait_seconds,
                }
                run.bump("dispatched")
                run.event(
                    "job",
                    mode=spec["mode"],
                    publisher=spec["label"],
                    jobId=job["jobId"],
                    status=job["status"],
                    lane="workbuddy",
                    leads=len(spec["leads"]),
                    waitSeconds=wait_seconds,
                    model=job.get("model"),
                )
            if not inflight:
                continue
            done, _ = futures.wait(list(inflight), return_when=futures.FIRST_COMPLETED)
            for future in done:
                entry = inflight.pop(future)
                try:
                    final = future.result()
                except Exception as error:  # noqa: BLE001 - 单组异常不阻断其它组
                    final = {"status": "error", "text": "", "error": error.__class__.__name__}
                text = (final or {}).get("text") or ""
                (run.dir / f"job-{entry['job']['jobId']}.txt").write_text(text, encoding="utf-8")
                parsed = dispatch.parse_candidates(text) or dispatch.parse_text_candidates(text)
                for candidate in parsed:
                    candidate["lane"] = "workbuddy"
                    candidate["mode"] = entry["mode"]  # 以任务本身为准，不信任模型回填的 mode
                wb_candidates.extend(parsed)
                status = (final or {}).get("status")
                if status not in ("succeeded", "done"):
                    lane_errors.append(
                        {
                            "lane": "workbuddy",
                            "mode": entry["mode"],
                            "id": entry["label"],
                            "leads": [lead["id"] for lead in entry["leads"]],
                            "status": status,
                        }
                    )
                if status == "timeout":
                    # 到点还没写完：真去取消，别让它继续吃 token（空转的成本比重新跑一次还高）
                    outcome = dispatch.cancel_job(entry["job"]["jobId"])
                    cancelled.append(entry["job"]["jobId"])
                    run.event("job_cancelled", jobId=entry["job"]["jobId"], ok=outcome.get("ok"), error=outcome.get("error"))
                run.event(
                    "job_done",
                    mode=entry["mode"],
                    publisher=entry["label"],
                    jobId=entry["job"]["jobId"],
                    status=status,
                    candidates=len(parsed),
                    waitSeconds=entry.get("waitSeconds"),
                )
            run.save()

        # ---- 收 DeepSeek ------------------------------------------------
        if ds_pool:
            for lead in selected:
                future = ds_futures.get(lead["id"])
                left = _remaining(deadline)
                if left <= BUDGET_RESERVE:
                    skipped_budget.append({"mode": "deepseek", "label": lead["id"], "leads": [lead["id"]]})
                    run.event("lane_skipped", lane="deepseek", lead=lead["id"], reason="budget")
                    continue
                try:
                    result = (
                        future.result(timeout=min(left - BUDGET_RESERVE, DS_LEAD_TIMEOUT))
                        if future
                        else {"ok": False, "error": "not_submitted", "items": []}
                    )
                except futures.TimeoutError:
                    run.event("lane_skipped", lane="deepseek", lead=lead["id"], reason="timeout")
                    skipped_budget.append({"mode": "deepseek", "label": lead["id"], "leads": [lead["id"]]})
                    continue
                except Exception as error:  # noqa: BLE001
                    result = {"ok": False, "error": error.__class__.__name__, "items": []}
                if not result.get("ok"):
                    lane_errors.append({"lane": "deepseek", "mode": "sweep", "id": lead["id"], "status": result.get("error")})
                    run.event("lane_error", lane="deepseek", lead=lead["id"], error=result.get("error"))
                    continue
                ds_candidates.extend(result.get("items") or [])
                run.event("lane_done", lane="deepseek", lead=lead["id"], candidates=len(result.get("items") or []))
    finally:
        if ds_pool:
            ds_pool.shutdown(wait=False, cancel_futures=True)
        pool.shutdown(wait=False, cancel_futures=True)

    sweep_hits = sum(1 for candidate in wb_candidates if candidate.get("mode") == "sweep")
    channel_hits = sum(1 for candidate in wb_candidates if candidate.get("mode") == "channel")
    run.state["feeds"] = {
        "workbuddy": len(wb_candidates),
        "deepseek": len(ds_candidates),
        "sweep": sweep_hits,
        "channel": channel_hits,
        "errors": len(lane_errors),
        "jobs": {"sweep": len(sweep_jobs), "channel": len(channel_jobs)},
        "budget": {
            "seconds": RUN_BUDGET_SECONDS,
            "skipped": len(skipped_budget),
            "cancelled": len(cancelled),
            "used": round(time.monotonic() - started, 1),
        },
    }
    if skipped_budget:
        run.state["skippedBudget"] = skipped_budget
    if lane_errors:
        run.state["laneErrors"] = lane_errors
    run.save()
    run.event("feeds", **run.state["feeds"])

    raw = wb_candidates + ds_candidates
    (run.dir / "candidates.json").write_text(
        json.dumps(
            {
                "sweep": [row for row in wb_candidates if row.get("mode") == "sweep"],
                "channel": [row for row in wb_candidates if row.get("mode") == "channel"],
                "deepseek": ds_candidates,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    # ---- 合并 + 验收 -------------------------------------------------
    run.stage("accepting")
    lead_by_id = {lead["id"]: lead for lead in selected}
    normalized = []
    for candidate in raw:
        lead = lead_by_id.get(candidate.get("leadId") or "")
        if lead is None:
            ip = str(candidate.get("ip") or "")
            lead = next((row for row in selected if norm(row.get("ip") or "") and norm(row.get("ip")) in norm(ip)), None)
        if lead is None:
            run.event("orphan_candidate", ip=candidate.get("ip"), name=candidate.get("officialName"))
            continue
        normalized.append(
            bag_accept.normalize_candidate(
                candidate,
                lead,
                str(candidate.get("lane") or "deepseek"),
                str(candidate.get("mode") or "sweep"),
            )
        )
    merged = bag_accept.merge(normalized)
    run.event("merged", raw=len(raw), merged=len(merged))

    try:
        existing = bag_table.list_bags()
        existing_keys = {f"{norm(row['ip'])}|{norm(row['officialName'])}" for row in existing}
    except Exception as error:  # noqa: BLE001
        existing, existing_keys = [], set()
        run.event("ledger_error", error=str(error)[:200])
        if write:
            run.finish("failed", f"读不到官方福袋表：{error}")
            return run

    page_cache: dict = {}
    records: list[dict] = []
    for candidate in merged:
        lead = lead_by_id[candidate["leadId"]]
        record = bag_accept.verify(candidate, lead, channels, page_cache, (since, until))
        key = f"{norm(record['ip'])}|{norm(record['officialName'])}"
        if key in existing_keys:
            record["reasons"] = list(record.get("reasons") or []) + ["duplicate"]
            record["status"] = "rejected"
        records.append(record)
        run.add_item(record)
        run.bump(record["status"].replace("pending_review", "pending"))

    # ---- 写表 --------------------------------------------------------
    run.stage("writing")
    accepted = [record for record in records if record["status"] == "accepted"]
    if write and accepted:
        rows = [{"values": bag_table.bag_values(record)} for record in accepted]
        bag_table.add_bags(rows, bag_table.empty_records())
        for record in accepted:
            record["written"] = True
        run.save()
        run.bump("written", len(rows))
        run.event("write", target="official_bags", count=len(rows))

    # ---- 回写线索 ----------------------------------------------------
    per_lead: dict[str, str] = {}
    for lead in selected:
        mine = [record for record in records if record.get("leadId") == lead["id"]]
        if any(record["status"] == "accepted" for record in mine):
            per_lead[lead["id"]] = "captured"
        elif any(record["status"] == "pending_review" for record in mine):
            per_lead[lead["id"]] = "partial"
        elif mine:
            per_lead[lead["id"]] = "empty"
        elif any(
            lead["id"] in (error.get("leads") or []) or error.get("id") in (lead["id"], lead.get("publisher"))
            for error in lane_errors
        ):
            per_lead[lead["id"]] = "error"
        else:
            per_lead[lead["id"]] = "empty"

    data = bag_leads.load()
    for lead in data["leads"]:
        if lead["id"] not in per_lead:
            continue
        lead["lastRunId"] = run.id
        lead["lastResult"] = per_lead[lead["id"]]
        if per_lead[lead["id"]] == "captured":
            lead["lastHitAt"] = today()
        lead["updatedAt"] = now_iso()
    bag_leads.save(data)
    run.event("leads_updated", results=per_lead)

    if skipped_budget or cancelled:
        run.finish(
            "partial",
            f"{RUN_BUDGET_SECONDS // 60} 分钟预算用尽：{len(cancelled)} 个 job 取消、{len(skipped_budget)} 项未跑",
        )
    else:
        run.finish("done" if not lane_errors else "partial", None if not lane_errors else "部分 lane 失败")
    return run
