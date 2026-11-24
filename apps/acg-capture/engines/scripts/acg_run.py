#!/usr/bin/env python3
"""ACG 官方赏抓取引擎（backfill / discover / snapshot）。

用法：
  python3 scripts/acg_run.py --snapshot                     # 只读：当前三张缺口
  python3 scripts/acg_run.py --kind backfill --dry-run      # 补齐：只产候选，不写表
  python3 scripts/acg_run.py --kind backfill --write        # 补齐：workbuddy + DeepSeek 双通道，验收通过后写表
  python3 scripts/acg_run.py --kind backfill --lanes deepseek --write   # 只走 DeepSeek 通道
  python3 scripts/acg_run.py --kind discover --dry-run      # 抓新品：上次成功日 - 1 天 → 今天

事件协议：stdout 每行 `@@ACG@@ {json}`；人看的进度走 stderr。
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acg import accept, brands, browser, channels, discover_ds, dispatch, feeds, gaps, products, table  # noqa: E402
from acg.common import (  # noqa: E402
    CHANNELS_FILE,
    DATA_DIR,
    LOCKS_DIR,
    RUNS_DIR,
    TZ,
    cell_text,
    extract_json,
    latest_run,
    norm,
    now_iso,
    today,
)
from acg.common import Run  # noqa: E402

BACKFILL_PROMPT = """补这些盘的官方信息：单抽价、每个赏各几个、整套抽数。
{items}
来源不限官方：官方/授权代理页优先（1kuji.com / on-line.1kuji.com / oneone.com.tw / cc1kuji.com），
小红书、微博、公众号、新闻站、活动站也能用——只要页面写明赏别、数量或单抽价；闲鱼/千岛/抖音拆卡这类二手交易页不要引用。
每个数字都要带来源 URL 和原文引用（quote 从页面正文原样抄，不要改写）。
写成「缺：整套子品结构」的盘，表里一条子品都还没有，需要把每个赏别都列出来（A、B、…、LAST），
name_cn 用页面上的赏名原样抄（不要自己翻译），alias 填日文原名（没有就空）；数量拿不到就把 count 写 null，但赏名和赏别必须齐。
quote 里只有「全 N 种」、没有「共 M 个」时，count 写 null——那 N 是款式数，不是一箱里的个数。
日版盘 currency 填 JPY，中国大陆版填 CNY；价格只认页面明写的数字，禁止推测、禁止按同 IP 类比。
每盘最多查 4 个页面；查不到就把该盘 prizes 写成 []、missing 里写「已查无公开信息」，不要反复换关键词。
只输出 JSON 数组，每个盘一个对象：
{{"pan":"","price":{{"value":null,"currency":"CNY","quote":"","source":""}},"total":null,"prizes":[{{"kind":"A","name_cn":"","alias":"","count":null,"quote":"","source":""}}],"missing":[]}}"""

DISCOVER_PROMPT = """窗口 {since} ~ {until}（北京时间）。这一轮要盯的品牌：{brands}

【浏览器已抓到的渠道原文】可以作为证据；source 用下面的 link 原样复制：
{feeds}

【表里已收录的赏盘】不要重复上报：
{existing}

任务：判断上面这些品牌在窗口内有没有上新赏盘（中国大陆版）。不限定渠道——微博、小红书、公众号、官网、新闻稿都行，你自己搜。
规则（宽松）：
- 品牌要覆盖全部；没上新的品牌不用报。
- 已发售、预告都报，stage 填「已发售」或「预告」；确切发售日拿不到就留空。
- source 必须是你实际打开过的 http(s) 页面；闲鱼/千岛/抖音拆卡这类二手交易页不要用。
- quote 从该页正文原样抄一段（≥8 字），能说明这盘存在；不要改写、不要拼接、不要编。
- name 用官方叫法写全（第几弹/系列名），brand 写盘名前缀。
- 不是赏盘的（纯周边、通贩、快闪、门店活动）不要报。
只输出 JSON 数组：[{{"brand":"","name":"","alias":"","release":"","stage":"已发售|预告","price":"","source":"","quote":""}}]"""


def _cell_plain(value) -> str:
    """cell_text 的反向：把富文本 cell（[{"text":"A","type":"text"}]）解回纯文本。"""
    if isinstance(value, str) and value.lstrip().startswith("["):
        try:
            parts = json.loads(value)
        except json.JSONDecodeError:
            return value
        if isinstance(parts, list):
            return "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))
    return str(value or "")


def log(message: str):
    print(f"[acg] {message}", file=sys.stderr, flush=True)


def acquire_lock(kind: str) -> Path:
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    lock = LOCKS_DIR / f"{kind}.lock"
    if lock.exists():
        try:
            pid = int(lock.read_text().strip() or 0)
        except ValueError:
            pid = 0
        if pid and _alive(pid):
            raise SystemExit(f"已有 {kind} 运行在跑（pid {pid}）")
        lock.unlink(missing_ok=True)
    lock.write_text(str(os.getpid()))
    return lock


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def snapshot() -> dict:
    pans = table.load_pans()
    subs = table.load_subs()
    result = gaps.compute(pans, subs)
    return {
        "at": today(),
        "stats": result["stats"],
        "batchPreview": [
            {"pan": item["pan"], "gaps": item["gaps"], "rows": item["rowCount"]}
            for item in gaps.pick_batch(result["byPan"], 6)
        ],
        "dedup": result["dedup"][:10],
    }


def _backfill_prompt(chunk: list[dict]) -> str:
    """一块盘的提示词：盘编号在块内重排，避免出现「盘20」这种跨批编号。"""
    lines = []
    for index, item in enumerate(chunk, 1):
        need = "、".join(
            {"price": "单抽价", "count": "各赏个数", "sub": "整套子品结构"}.get(gap, gap)
            for gap in item["gaps"]
        )
        lines.append(f"盘{index}：{item['pan']}｜别名：{item['alias'] or '无'}｜缺：{need}")
    return BACKFILL_PROMPT.format(items="\n".join(lines))


# 社交通道单轮最多补几个盘：每盘要开 2 个平台 × 2 个词，多开就是给风控送人头
SOCIAL_MAX_PANS = 6


def _run_social_lane(pans: list[dict], run: Run, budget: float) -> dict:
    """社媒通道：串行逐盘（风控优先），预算内能跑几个跑几个，命中风控立即停。"""
    from acg import social as social_mod

    started = time.time()
    items: list[dict] = []
    errors: list[str] = []
    workdir = run.dir / "social"
    done = 0
    blocked_hit = ""
    for index, pan in enumerate(pans):
        if time.time() - started > budget:
            errors.append("lane_budget_exhausted")
            break
        if index:
            # 盘与盘之间也要停一下：连着开搜索页是小红书风控最常见的触发方式
            time.sleep(random.uniform(6, 12))
        result = social_mod.social_pan(pan, workdir)
        done += 1
        items.extend(result.get("items") or [])
        error = str(result.get("error") or "")
        if not result.get("ok"):
            errors.append(f"{pan.get('pan')}:{error}")
            if error.startswith("blocked") or "cooldown" in error:
                blocked_hit = error
                break  # 风控命中就停：后续盘不再发请求
    return {
        "items": items,
        "errors": errors,
        "pans": done,
        "blocked": blocked_hit,
        "elapsed": round(time.time() - started, 1),
    }


def _submit_backfill_chunk(run: Run, chunk: list[dict], index: int, total: int, attempt: int = 1):
    """派一块（≤ LANE_CHUNK_SIZE 盘）；提交失败按 LANE_RETRY 再试。返回 (job, error)。"""
    prompt = _backfill_prompt(chunk)
    last_error = ""
    for try_no in range(attempt, attempt + dispatch.LANE_RETRY + 1):
        try:
            job = dispatch.submit_workbuddy(
                prompt,
                f"acg-backfill-{run.id[-6:]}-c{index}-t{try_no}",
                run.dir / "jobs",
            )
        except Exception as error:  # noqa: BLE001 - 单块派不出去只废这块，不拖垮整轮
            last_error = str(error)[:300]
            run.event("job_submit_failed", chunk=index, attempt=try_no, error=last_error)
            continue
        run.state["params"].setdefault("jobIds", []).append(job["jobId"])
        run.state["params"].setdefault("jobId", job["jobId"])
        run.save()
        run.bump("dispatched")
        run.event(
            "job", jobId=job["jobId"], kind="workbuddy", status=job["status"],
            model=job.get("model"), purpose="backfill", pans=len(chunk),
            chunk=index, chunks=total, attempt=try_no,
        )
        return job, ""
    return None, last_error


def _wait_backfill_chunks(run: Run, entries: list[dict], timeout: int) -> None:
    """并发等一批 job；终态写回 entry，结果文本存进 entry["text"]。"""
    if not entries:
        return
    states = dispatch.wait_jobs([entry["job"]["resultPath"] for entry in entries], timeout=timeout, interval=5)
    for entry, state in zip(entries, states):
        status = (str(state.get("status") or "").lower()) or "unknown"
        text = state.get("text") or ""
        entry["status"] = status
        entry["chars"] = len(text)
        entry["text"] = text
        entry["error"] = dispatch.job_error(state)
        run.event(
            "job_done", jobId=entry["job"]["jobId"], status=status, chars=len(text),
            chunk=entry["chunk"], error=entry["error"],
        )
        if status == "succeeded":
            run.bump("done")


def backfill(
    run: Run,
    batch_size: int,
    use_agent: bool,
    write: bool,
    wait: int = 1200,
    lanes: list[str] | tuple[str, ...] = ("workbuddy", "deepseek"),
    pan_filters: list[str] | tuple[str, ...] = (),
    gap_filters: list[str] | tuple[str, ...] = (),
) -> None:
    run.stage("preparing")
    pans = table.load_pans()
    subs = table.load_subs()
    result = gaps.compute(pans, subs)
    run.set_table(**result["stats"])
    run.event("gaps", stats=result["stats"], dedup=len(result["dedup"]))
    log(f"表：赏盘 {result['stats']['pans']} / 子品 {result['stats']['subs']}")

    filters = [str(k).strip() for k in pan_filters if str(k).strip()]
    gap_types = [str(k).strip() for k in gap_filters if str(k).strip()]
    if filters or gap_types:
        # 定向补几个盘：先拿全量队列再筛，避免「再跑一轮又派到同一个大批次」把已确认无源的盘重派
        picked = gaps.pick_batch(result["byPan"], 999)
        if filters:
            picked = [item for item in picked if any(key in item["pan"] for key in filters)]
        if gap_types:
            picked = [item for item in picked if any(gap in item["gaps"] for gap in gap_types)]
        batch = picked[:batch_size]
    else:
        batch = gaps.pick_batch(result["byPan"], batch_size)
    run.state["batch"] = batch
    run.state["scope"] = {
        "mode": "fill_gaps",
        "batchSize": batch_size,
        "pans": [{"name": item.get("pan", ""), "gaps": item.get("gaps") or []} for item in batch],
    }
    run.save()
    run.state["params"]["batchSize"] = batch_size
    run.state["params"]["batch"] = [item["pan"] for item in batch]
    run.save()
    run.event("batch", items=[{"pan": b["pan"], "gaps": b["gaps"], "rows": b["rowCount"]} for b in batch])
    if not batch:
        run.finish("done")
        return

    if not use_agent:
        run.finish("done")
        return

    run.stage("dispatch")
    lanes = [str(name).strip() for name in lanes if str(name).strip()]
    use_wb = "workbuddy" in lanes
    use_ds = "deepseek" in lanes
    use_social = "social" in lanes
    run.state["params"]["lanes"] = lanes
    run.save()

    chunks = dispatch.chunk(batch, dispatch.LANE_CHUNK_SIZE)
    ledger = {
        lane: {
            "requested": lane in lanes,
            "ok": True if lane in lanes else None,
            "error": "",
            "pans": len(batch),
            "candidates": 0,
            "jobs": [],
        }
        for lane in ("workbuddy", "deepseek", "social")
    }
    # 社交通道是「补充」：被平台风控挡掉不该让整轮变 partial，但必须在台账里写清楚
    ledger["social"]["optional"] = True

    # workbuddy：一块 ≤ LANE_CHUNK_SIZE 盘。19 盘塞一个 job 时每盘只回赏名、个数全空（2026-11-23 实测）。
    job_runs: list[dict] = []
    if use_wb:
        pre = dispatch.preflight_workbuddy()
        run.event(
            "lane_preflight", lane="workbuddy", ok=pre["ok"],
            error=pre["error"], detail=pre.get("detail") or {},
        )
        if pre["ok"] and (pre.get("detail") or {}).get("repaired"):
            run.event("lane_repair", lane="workbuddy", action="recreate_local_agent_wrapper")
            log("local-agent 包装脚本缺失，已按已安装的 bridge 复原")
        if not pre["ok"]:
            ledger["workbuddy"]["ok"] = False
            ledger["workbuddy"]["error"] = pre["error"]
            log(f"workbuddy 通道未就绪：{pre['error']}")
        else:
            # 一波最多 LANE_MAX_JOBS 个 job：每个 job 是一个 Electron 进程，4 个同时起会互相拖慢
            for wave_start in range(0, len(chunks), dispatch.LANE_MAX_JOBS):
                wave = chunks[wave_start:wave_start + dispatch.LANE_MAX_JOBS]
                entries: list[dict] = []
                for offset, piece in enumerate(wave):
                    chunk_index = wave_start + offset + 1
                    job, error = _submit_backfill_chunk(run, piece, chunk_index, len(chunks))
                    if job is None:
                        ledger["workbuddy"]["ok"] = False
                        ledger["workbuddy"]["error"] = f"chunk{chunk_index}_submit_failed:{error}"
                        continue
                    entries.append(
                        {
                            "chunk": chunk_index, "job": job, "pans": len(piece),
                            "status": "", "chars": 0, "text": "", "error": "",
                        }
                    )
                if not entries:
                    continue
                run.stage("waiting")
                timeout = min(3600, max(wait, 90 * dispatch.LANE_CHUNK_SIZE))
                run.event(
                    "wait", timeout=timeout, pans=sum(entry["pans"] for entry in entries),
                    jobs=len(entries), chunkSize=dispatch.LANE_CHUNK_SIZE,
                    wave=wave_start // dispatch.LANE_MAX_JOBS + 1,
                )
                _wait_backfill_chunks(run, entries, timeout)
                job_runs.extend(entries)

    # DeepSeek 通道和 workbuddy 同时开跑：同一批盘，各答一部分，最后在同一个验收层合并，口径不变。
    ds_pool = None
    ds_future = None
    if use_ds:
        from acg import backfill_ds

        pre = dispatch.preflight_deepseek()
        run.event(
            "lane_preflight", lane="deepseek", ok=pre["ok"],
            error=pre["error"], detail=pre.get("detail") or {},
        )
        if not pre["ok"]:
            ledger["deepseek"]["ok"] = False
            ledger["deepseek"]["error"] = pre["error"]
            log(f"DeepSeek 通道未就绪：{pre['error']}")
        else:
            ds_pool = ThreadPoolExecutor(max_workers=1)
            ds_future = ds_pool.submit(backfill_ds.run_pans, batch, 4)
            run.event("lane", lane="deepseek", status="running", pans=len(batch))

    # 社媒通道（微博 / 小红书）：只补结构类缺口，单轮 ≤ SOCIAL_MAX_PANS 盘；命中风控就整条停并冷却。
    social_pool = None
    social_future = None
    social_batch: list[dict] = []
    if use_social:
        from acg import social

        social_batch = [item for item in batch if {"sub", "count"} & set(item["gaps"])][:SOCIAL_MAX_PANS]
        ready = social.available()
        cool = social.cooldown()
        run.event(
            "lane_preflight", lane="social", ok=bool(ready and not cool),
            error=("cooldown" if cool else ("" if ready else "ego_browser_unavailable")),
            detail={"pans": len(social_batch), "cooldown": cool or {}},
        )
        if cool:
            ledger["social"]["ok"] = False
            ledger["social"]["error"] = f"cooldown_until:{cool.get('until')}"
            log(f"社交通道冷却中（{cool.get('until')}），本轮跳过")
        elif not ready:
            ledger["social"]["ok"] = False
            ledger["social"]["error"] = "ego_browser_unavailable"
            log("社交通道未就绪：ego-browser 不可用")
        elif not social_batch:
            ledger["social"]["error"] = "no_structural_gap"
            run.event("lane", lane="social", status="skipped", reason="no_structural_gap")
        else:
            social_pool = ThreadPoolExecutor(max_workers=1)
            social_future = social_pool.submit(
                _run_social_lane, social_batch, run, 90 * len(social_batch) + 120
            )
            run.event("lane", lane="social", status="running", pans=len(social_batch))

    if job_runs:
        timeout = min(3600, max(wait, 90 * dispatch.LANE_CHUNK_SIZE))
        stale = [entry for entry in job_runs if entry["status"] != "succeeded"]
        if stale and dispatch.LANE_RETRY:
            # 起步就死 / 中断的块再派一次：2026-11-23 那次 job 在 launch 阶段 interrupted，
            # 一次重试就能拿到结果，不重试整批白跑。
            run.event("job_retry", jobs=[entry["job"]["jobId"] for entry in stale], count=len(stale))
            retries: list[dict] = []
            for entry in stale:
                piece = chunks[entry["chunk"] - 1]
                job, _error = _submit_backfill_chunk(run, piece, entry["chunk"], len(chunks), attempt=2)
                if job is None:
                    continue
                retries.append(
                    {
                        "chunk": entry["chunk"], "job": job, "pans": len(piece),
                        "status": "", "chars": 0, "text": "", "error": "",
                    }
                )
            if retries:
                _wait_backfill_chunks(run, retries, timeout)
                job_runs.extend(retries)

    # 同一块重试过就只认最后一次：失败那次的输出不参与验收，也不影响通道判定
    final_by_chunk: dict[int, dict] = {}
    for entry in job_runs:
        final_by_chunk[entry["chunk"]] = entry
    final_runs = list(final_by_chunk.values())

    if use_wb and ledger["workbuddy"]["ok"]:
        failed_chunks = [entry for entry in final_runs if entry["status"] != "succeeded"]
        if failed_chunks:
            ledger["workbuddy"]["ok"] = False
            ledger["workbuddy"]["error"] = "; ".join(
                f"chunk{entry['chunk']}:{entry['status'] or 'unknown'}"
                + (f":{entry['error'][:120]}" if entry["error"] else "")
                for entry in failed_chunks
            )

    ds_result = {"items": [], "perPan": {}, "errors": [], "elapsed": 0.0}
    if ds_future:
        try:
            ds_result = ds_future.result(timeout=wait)
            run.event(
                "lane",
                lane="deepseek",
                status="done",
                items=len(ds_result.get("items") or []),
                sources=ds_result.get("sources"),
                elapsed=ds_result.get("elapsed"),
                failed=len(ds_result.get("errors") or []),
            )
        except Exception as error:  # noqa: BLE001 - 通道超时/失败只降级，不拖垮本轮
            run.event("lane", lane="deepseek", status="timeout", error=str(error)[:200])
            ledger["deepseek"]["ok"] = False
            ledger["deepseek"]["error"] = f"lane_timeout:{str(error)[:160]}"
        finally:
            ds_pool.shutdown(wait=False, cancel_futures=True)

    if use_ds and ledger["deepseek"]["ok"]:
        ds_errors = ds_result.get("errors") or []
        if batch and not ds_result.get("items") and len(ds_errors) >= len(batch):
            # 整批盘都取数失败＝通道没工作，不能当成「来源未公布」混过去
            ledger["deepseek"]["ok"] = False
            ledger["deepseek"]["error"] = f"all_pans_failed:{str(ds_errors[0])[:120]}"

    social_result = {"items": [], "errors": [], "pans": 0, "elapsed": 0.0}
    if social_future:
        try:
            social_result = social_future.result(timeout=max(60, 90 * len(social_batch) + 120))
            run.event(
                "lane", lane="social", status="done",
                items=len(social_result.get("items") or []),
                pans=social_result.get("pans"),
                elapsed=social_result.get("elapsed"),
                failed=len(social_result.get("errors") or []),
            )
        except Exception as error:  # noqa: BLE001 - 补充通道失败不影响主通道
            run.event("lane", lane="social", status="timeout", error=str(error)[:200])
            social_result["errors"] = [f"lane_timeout:{str(error)[:160]}"]
        finally:
            social_pool.shutdown(wait=False, cancel_futures=True)

    if use_social and ledger["social"]["ok"]:
        social_errors = social_result.get("errors") or []
        if social_result.get("blocked"):
            ledger["social"]["ok"] = False
            ledger["social"]["error"] = str(social_result["blocked"])[:160]
        elif not social_result.get("items") and social_errors and len(social_errors) >= len(social_batch) > 0:
            ledger["social"]["ok"] = False
            ledger["social"]["error"] = f"all_pans_failed:{social_errors[0][:120]}"

    wb_candidates: list[dict] = []
    for entry in final_runs:
        for candidate in dispatch.parse_candidates(entry.get("text") or ""):
            candidate["lane"] = "workbuddy"
            wb_candidates.append(candidate)
    ds_items = [dict(item, lane="deepseek") for item in (ds_result.get("items") or []) if isinstance(item, dict)]
    social_items = [
        dict(item, lane="social") for item in (social_result.get("items") or []) if isinstance(item, dict)
    ]
    ledger["workbuddy"]["candidates"] = len(wb_candidates)
    ledger["deepseek"]["candidates"] = len(ds_items)
    ledger["social"]["candidates"] = len(social_items)
    ledger["social"]["pans"] = len(social_batch)
    ledger["workbuddy"]["jobs"] = [
        {
            "jobId": entry["job"]["jobId"], "chunk": entry["chunk"], "pans": entry["pans"],
            "status": entry["status"], "chars": entry["chars"],
        }
        for entry in job_runs
    ]
    texts = [entry.get("text") or "" for entry in final_runs if entry.get("text")]

    (run.dir / "candidates.json").write_text(
        json.dumps(
            {
                "job": job_runs[0]["job"] if job_runs else {"status": "skipped"},
                "text": "\n\n".join(texts),
                "texts": texts,
                "jobs": [
                    {**entry["job"], "status": entry["status"], "chars": entry["chars"]}
                    for entry in job_runs
                ],
                "deepseek": ds_result,
                "social": social_result,
                "lanes": ledger,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    run.stage("accepting")
    candidates = list(wb_candidates) + list(ds_items) + list(social_items)
    run.event(
        "candidates", count=len(candidates), workbuddy=len(wb_candidates),
        deepseek=len(ds_items), social=len(social_items),
    )
    job_timeout = bool(job_runs) and all(entry["status"] == "timeout" for entry in job_runs)
    page_cache: dict = {}
    render = page_renderer(run.dir / "feeds")
    ocr = ocr_reader(run.dir / "ocr")
    records = []
    for item in batch:
        matched = accept.match_all(item, candidates)
        candidate = accept.merge_candidates(matched)
        record = accept.verify_item(item, candidate, page_cache, render, ocr)
        if job_timeout and not matched:
            record["reasons"] = ["agent_timeout"]
        records.append(record)
        run.add_item(record)
        if record["status"] == "accepted":
            run.bump("accepted")
        elif record["status"] == "rejected":
            run.bump("rejected")
        elif record["status"] == "pending_review":
            run.bump("pending")
        else:
            # 来源未公布：不需要人确认，和「待确认」分开计数，否则待确认队列会被没有可确认内容的条目灌满
            run.bump("unavailable")

    run.stage("writing")
    plan = build_write_plan(records, batch)
    run.event("write_plan", dryRun=not write, plan=plan)
    if write:
        apply_write_plan(run, records, batch, plan)

    # 通道台账落到 run.json：哪个通道派没派出去、拿没拿到结果，一眼能看，不再靠翻 events。
    run.state["lanes"] = ledger
    run.save()
    run.event("lanes", **ledger)
    requested = [lane for lane in ("workbuddy", "deepseek", "social") if ledger[lane]["requested"]]
    log(
        "通道："
        + "；".join(
            f"{lane} {'已就绪' if ledger[lane]['ok'] else '未就绪'}"
            f"（{len(ledger[lane]['jobs'])} 个 job / {ledger[lane]['candidates']} 条候选）"
            for lane in requested
        )
    )
    missing = [lane for lane in requested if not ledger[lane]["ok"] and not ledger[lane].get("optional")]
    optional_missing = [lane for lane in requested if not ledger[lane]["ok"] and ledger[lane].get("optional")]
    if optional_missing:
        # 社媒被风控挡掉是常态，写进 warnings 和台账，不让整轮变 partial
        detail = "；".join(f"{lane}: {ledger[lane]['error'] or '未产出'}" for lane in optional_missing)
        run.state.setdefault("warnings", []).append(f"optional_lane_down:{detail}"[:300])
        log(f"补充通道未完成（不影响主流程）：{detail}")
    if missing:
        detail = "；".join(f"{lane}: {ledger[lane]['error'] or '未产出'}" for lane in missing)
        # 通道没跑通就不能报成功：状态记 partial、退出码非 0，调度那边才会当失败处理
        run.finish("partial", f"通道未完成：{detail}"[:500])
    else:
        run.finish("done")


def build_write_plan(records: list[dict], batch: list[dict]) -> dict:
    by_id = {item["panRecordId"]: item for item in batch}
    price_updates = []
    count_updates = []
    sub_adds = []
    for record in records:
        if record["status"] != "accepted":
            continue
        item = by_id.get(record["panRecordId"]) or {}
        if record.get("price"):
            price = record["price"]
            updates = {"单抽价": cell_text(table.price_cell(price["value"], price["currency"], False))}
            price_updates.append({"record_id": record["panRecordId"], "values": updates})
        if record.get("counts"):
            rows = {row["kind"]: row for row in item.get("rows", [])}
            for prize in record["counts"]:
                row = rows.get(prize["kind"])
                if row:
                    count_updates.append(
                        {"record_id": row["recordId"], "values": {"单套数量": int(prize["count"])}}
                    )
        if record.get("subs"):
            # 无子品的盘：这一批赏名是新建行，不是更新已有行
            for prize in record["subs"]:
                sub_adds.append(
                    {"values": table.sub_values_for_new(
                        record["panRecordId"], record.get("pan") or item.get("pan") or "", prize)}
                )
    return {"price": price_updates, "counts": count_updates, "subs": sub_adds}


def apply_write_plan(run: Run, records: list[dict], batch: list[dict], plan: dict) -> None:
    written = 0
    # 子品行 id → 盘 record_id：数量写成功要回填到「盘」这条结论上
    sub_to_pan = {
        str(row.get("recordId")): item.get("panRecordId")
        for item in batch
        for row in item.get("rows") or []
    }
    price_ids = {str(row["record_id"]) for row in plan["price"]}
    count_pans = {sub_to_pan.get(str(row["record_id"])) for row in plan["counts"]} - {None}
    if plan["price"]:
        grouped = [{"record_id": row["record_id"], "values": row["values"]} for row in plan["price"]]
        table.update_pans(grouped)
        written += len(grouped)
        run.event("write", target="price", count=len(grouped))
    for index in range(0, len(plan["counts"]), 10):
        chunk = plan["counts"][index : index + 10]
        table.update_subs(chunk)
        written += len(chunk)
        run.event("write", target="counts", count=len(chunk))

    added_pans: set[str] = set()
    sub_adds = plan.get("subs") or []
    if sub_adds:
        # 先回读一遍：同一盘已经有子品的直接跳过，避免重跑/人工采信把结构写两遍
        have = {row["pan_rid"] for row in table.load_subs() if row["pan_rid"]}
        fresh = [
            row for row in sub_adds
            if (row["values"].get("关联") or [{}])[0].get("record_id") not in have
        ]
        skipped = len(sub_adds) - len(fresh)
        if skipped:
            run.event("write", target="subs_skip_existing", count=skipped)
        for index in range(0, len(fresh), 50):
            chunk = fresh[index : index + 50]
            table.add_subs(chunk)
            written += len(chunk)
            for row in chunk:
                rid = (row["values"].get("关联") or [{}])[0].get("record_id")
                if rid:
                    added_pans.add(str(rid))
            run.event("write", target="subs", count=len(chunk))

    run.set_count("written", written)
    for record in records:
        if record["status"] != "accepted":
            continue
        parts = []
        if str(record.get("panRecordId")) in price_ids:
            parts.append("价格")
        if record.get("panRecordId") in count_pans:
            parts.append("数量")
        if str(record.get("panRecordId")) in added_pans:
            parts.append("子品结构")
        record["written"] = bool(parts)
        record["writtenParts"] = parts
    run.save()
    # 回读校验：数量是否真的落库
    subs = table.load_subs()
    index = {(row["rid"]): row for row in subs}
    missing = []
    for row in plan["counts"]:
        current = index.get(row["record_id"])
        if not current or current["qty"] != row["values"]["单套数量"]:
            missing.append(row["record_id"])
    run.event("write_verify", checked=len(plan["counts"]), mismatch=len(missing), ids=missing[:10])

    # 子品行建完也要回读：行在不在、有没有真的挂到这个盘上、数量对不对
    if sub_adds:
        by_pan_kind = {(row["pan_rid"], row["kind"]): row for row in subs}
        bad = []
        for row in sub_adds:
            values = row["values"]
            pan_rid = (values.get("关联") or [{}])[0].get("record_id")
            # 写入时「赏别」是 cell_text 富文本 JSON，回读是纯字母；不还原就永远是 mismatch
            kind = _cell_plain(values.get("赏别"))
            current = by_pan_kind.get((pan_rid, kind))
            if not current:
                bad.append({"pan": pan_rid, "kind": kind, "reason": "missing"})
                continue
            expect_qty = values.get("单套数量")
            if expect_qty is not None and current["qty"] != expect_qty:
                bad.append({"pan": pan_rid, "kind": kind, "reason": "qty_mismatch"})
        run.event("write_verify_subs", checked=len(sub_adds), mismatch=len(bad), items=bad[:10])


def _weibo_uid(url: str) -> str:
    """渠道里存的是账号页 URL（m.weibo.cn/u/<uid>），抓取脚本只要 uid。"""
    text = str(url or "").strip()
    if text.startswith("uid:"):
        return text.split(":", 1)[1].strip()
    for segment in re.split(r"[/?#]", text):
        if segment.isdigit() and len(segment) >= 5:
            return segment
    return ""


def discover(run: Run, since: str, until: str, use_agent: bool, write: bool,
             pages: int = 2, wait_seconds: int = 1800) -> None:
    """抓新品（2026-11-20 简化版）：三路并行取证，一个验收层。

    1) 浏览器通道：渠道表里 xhs / static / weibo 的精确账号页，用 ego-browser 抓原文落快照；
    2) workbuddy 通道：一个 job 覆盖全部品牌，不指定渠道；
    3) DeepSeek 通道：按品牌搜索 + 抽取，同样不限渠道。

    三路候选按盘名去重后统一走 verify_discover：来源能打开 + quote 命中才算数，
    所以「两个模型都这么说」不算证据。品牌清单来自企微「品牌」tab，不在这里维护。
    """
    run.stage("preparing")
    run.state["params"].update({"since": since, "until": until, "pages": pages, "waitSeconds": wait_seconds})
    brand_rows = brands.load()
    brand_names = [row["name"] for row in brand_rows]
    registry = channels.load()
    confirmed = [row for row in registry.get("brands", []) if row.get("status") == "confirmed"]
    browser_rows = [
        row
        for row in confirmed
        if (row.get("type") or "") in ("weibo", "xhs", "static")
        and str(row.get("url") or "").startswith("http")
        and (row.get("scope") or "cn") == "cn"
    ]
    run.set_table(brands=len(brand_names), channels=len(browser_rows))
    run.event("brands", total=len(brand_names), browser=len(browser_rows))
    if not brand_names:
        run.finish("failed", "品牌清单为空：先对齐企微「品牌」tab（q979lj）")
        return

    pans_before = table.load_pans()
    existing = {accept.pan_key(pan["name"], pan["brand"]) for pan in pans_before}
    existing_names = [pan["name"] for pan in pans_before if pan.get("name")]
    run.state["scope"] = {
        "mode": "new_pans",
        "window": {"since": since, "until": until},
        "brands": brand_names,
        "channels": {"browser": len(browser_rows)},
        "pages": pages,
    }
    run.save()

    items, captured, feed_errors = pull_feeds(run, browser_rows, since, until, pages)
    save_feeds(run, items, captured, feed_errors)
    run.state["feeds"] = {"items": len(items), "channels": len(captured), "errors": len(feed_errors)}
    run.save()
    snapshots = feeds.snapshot_index(items)

    if not use_agent:
        run.finish("done")
        return

    # DeepSeek 通道和 workbuddy 同时开跑：两条独立取证，最后合并到同一个验收层。
    run.stage("searching")
    ds_pool = ThreadPoolExecutor(max_workers=1)
    ds_future = ds_pool.submit(discover_ds.run, brand_names, since, until, 3)
    run.event("lane", lane="deepseek", status="running", brands=len(brand_names))

    run.stage("dispatch")
    job = dispatch_wide(run, brand_names, items, existing_names)
    run.state["jobs"] = [job]
    run.bump("dispatched")
    run.event(
        "job", jobId=job["jobId"], kind="workbuddy", status=job["status"],
        model=job.get("model"), purpose="discover:wide", brands=len(brand_names),
    )

    run.stage("waiting")
    result = dispatch.wait_job(job["resultPath"], timeout=wait_seconds, interval=5)
    text = str(result.get("text") or "")
    job["status"] = str(result.get("status") or "unknown")
    job["chars"] = len(text)
    wb_candidates = dispatch.parse_candidates(text) if text else []
    run.event(
        "job_done", jobId=job["jobId"], status=job["status"], chars=len(text),
        candidates=len(wb_candidates),
    )

    ds_result: dict = {"items": [], "perBrand": {}, "errors": [], "elapsed": 0.0, "sources": 0}
    try:
        ds_result = ds_future.result(timeout=max(120, wait_seconds))
        run.event(
            "lane", lane="deepseek", status="done", items=len(ds_result.get("items") or []),
            sources=ds_result.get("sources"), elapsed=ds_result.get("elapsed"),
            failed=len(ds_result.get("errors") or []),
        )
    except Exception as error:  # noqa: BLE001 - 单个通道失败不拖垮整轮
        run.event("lane", lane="deepseek", status="timeout", error=str(error)[:200])
    finally:
        ds_pool.shutdown(wait=False, cancel_futures=True)

    (run.dir / "candidates.json").write_text(
        json.dumps({"job": job, "text": text, "deepseek": ds_result}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    run.state["answer"] = {
        "workbuddy": len(wb_candidates),
        "deepseek": len(ds_result.get("items") or []),
    }
    run.save()

    candidates = []
    seen_keys: set[str] = set()
    for candidate in list(wb_candidates) + list(ds_result.get("items") or []):
        if not isinstance(candidate, dict):
            continue
        key = accept.pan_key(
            str(candidate.get("name") or candidate.get("pan") or ""),
            str(candidate.get("brand") or ""),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        candidates.append(candidate)
    run.event(
        "candidates", count=len(candidates),
        workbuddy=len(wb_candidates), deepseek=len(ds_result.get("items") or []),
    )
    run.bump("done")

    accept_and_write(run, candidates, existing, snapshots, write)

    if job["status"] == "timeout":
        run.finish("partial", f"agent_timeout：workbuddy 超时，结果可 --resume {run.id} 回收")
    else:
        run.finish("done")


def pull_feeds(run: Run, confirmed: list[dict], since: str, until: str, pages: int) -> tuple[list[dict], set, list[dict]]:
    """抓 xhs / static / weibo 的指定页面。同一个账号被多个品牌共用时只抓一次。"""
    run.stage("pulling")
    feed_dir = run.dir / "feeds"
    feed_dir.mkdir(parents=True, exist_ok=True)
    for stale in feed_dir.glob("_ego_job_*.mjs"):  # 上次被强杀留下的包装脚本
        stale.unlink(missing_ok=True)

    targets = [row for row in confirmed if (row.get("type") or "") in ("weibo", "xhs", "static")]
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in targets:
        key = (str(row.get("type") or ""), str(row.get("url") or ""))
        groups.setdefault(key, []).append(row)

    items: list[dict] = []
    captured: set[str] = set()
    errors: list[dict] = []
    if not targets:
        return items, captured, errors
    if not browser.available():
        run.event("feeds", items=0, channels=0, errors=len(groups), reason="ego_browser_missing")
        log("ego-browser 不可用：浏览器通道本轮为空，靠 workbuddy / DeepSeek 两路")
        return items, captured, [{"channelId": row.get("id"), "error": "ego_browser_missing"} for row in targets]

    def one(rows: list[dict]):
        row = rows[0]
        shared = [r.get("brand") for r in rows]
        kind = str(row.get("type") or "")
        url = str(row.get("url") or "")
        try:
            if kind == "weibo":
                ok, posts, error = browser.weibo_posts(_weibo_uid(url), pages, feed_dir, timeout=120)
                if not ok:
                    return rows, [], error
                got = feeds.weibo_items(row.get("brand") or "", row.get("channel") or "", posts, since, until)
            elif kind == "xhs":
                ok, notes, error = browser.xhs_notes(url, max(2, pages * 2), feed_dir, timeout=150)
                if not ok:
                    return rows, [], error
                got = feeds.xhs_items(row.get("brand") or "", row.get("channel") or "", notes)
            else:  # static：整页正文进快照，验收直接命中
                ok, text, error = browser.page_text(url, feed_dir, timeout=90)
                if not ok or not text.strip():
                    return rows, [], error or "empty_page"
                got = [
                    {
                        "brand": row.get("brand") or "",
                        "channel": row.get("channel") or "",
                        "type": "static",
                        "id": url,
                        "url": url,
                        "date": "",
                        "text": text.strip()[:20000],
                        "evidence": "static_page",
                        "undated": True,
                    }
                ]
            for item in got:
                item["brands"] = shared  # 共用官号：几个品牌一起标，验收仍按盘名前缀定品牌
            return rows, got, ""
        except Exception as error:  # noqa: BLE001 - 单渠道异常只记错误
            return rows, [], f"{error.__class__.__name__}:{error}"

    with ThreadPoolExecutor(max_workers=5) as pool:
        for rows, got, error in pool.map(one, groups.values()):
            if error:
                for row in rows:
                    errors.append({"channelId": row.get("id"), "channel": row.get("channel"), "error": error})
                continue
            for row in rows:
                captured.add(row.get("id"))
            items.extend(got)

    run.event("feeds", items=len(items), channels=len(captured), errors=len(errors))
    log(f"渠道原文：{len(items)} 条（{len(captured)}/{len(targets)} 个渠道，{len(groups)} 个号），失败 {len(errors)}")
    return items, captured, errors


def save_feeds(run: Run, items: list[dict], captured: set, errors: list[dict],
               ds_hits: list[dict] | None = None) -> None:
    payload = {
        "items": items,
        "captured": sorted(x for x in captured if x),
        "errors": errors,
        "dsHits": ds_hits or [],
    }
    (run.dir / "feeds.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def load_feeds(run_dir: Path) -> tuple[list[dict], set, list[dict], list[dict]]:
    path = run_dir / "feeds.json"
    if not path.exists():
        return [], set(), [], []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], set(), [], []
    return (
        payload.get("items") or [],
        set(payload.get("captured") or []),
        payload.get("errors") or [],
        payload.get("dsHits") or [],
    )


def dispatch_wide(run: Run, brand_names: list[str], items: list[dict], existing_names: list[str]) -> dict:
    """一个 job 覆盖全部品牌：不指定渠道，只给品牌 + 已抓原文 + 去重名单。"""
    feed_block = feeds.digest(items) or "（本轮浏览器通道没有抓到原文）"
    existing_block = "、".join(existing_names[:150]) or "（空表）"
    params = run.state.get("params") or {}
    prompt = DISCOVER_PROMPT.format(
        since=params.get("since") or "",
        until=params.get("until") or "",
        brands="、".join(brand_names),
        feeds=feed_block,
        existing=existing_block,
    )
    title = f"acg-discover-{run.id[-6:]}-all"
    job = dispatch.submit_workbuddy(prompt, title, run.dir / "jobs")
    return {
        "jobId": job["jobId"],
        "status": job["status"],
        "resultPath": job["resultPath"],
        "brands": brand_names,
        "channels": len(items),
        "title": title,
        "model": job.get("model"),
    }



def ocr_reader(workdir: Path, timeout: int = 120):
    """验收层用的 OCR 兜底：正文里没有的原文，可能印在配图里（公众号图鉴、小红书九宫格）。

    与 render 同一分工：只换「怎么拿到原文」，判定口径（原文命中 + 数字一致）不变。
    按 URL 缓存，同一页只 OCR 一次。
    """
    from acg import ocr as ocr_mod

    cache: dict[str, str] = {}

    def read(url: str) -> str:
        if url in cache:
            return cache[url]
        text = ocr_mod.page_ocr(url, workdir, timeout=timeout) if ocr_mod.available() else ""
        cache[url] = text
        return text

    return read


def page_renderer(workdir: Path, timeout: int = 75):
    """验收层用的渲染兜底：urllib 打不开或只拿到 JS 壳时，用登录态浏览器渲染一次。

    与抓取层的分工一样：这里只换「怎么拿到正文」，不放松任何判定口径。
    按 URL 缓存，同一页只渲染一次。
    """
    cache: dict[str, str] = {}

    def render(url: str) -> str:
        if url in cache:
            return cache[url]
        text = ""
        if browser.available():
            for _ in range(2):  # 浏览器冷启动偶尔空返，重试一次再判
                ok, body, _ = browser.page_text(url, workdir, timeout=timeout)
                if ok and body.strip():
                    text = body
                    break
        cache[url] = text
        return text

    return render


def accept_and_write(run: Run, candidates: list[dict], existing: set[str],
                     snapshots: dict, write: bool) -> list[dict]:
    """逐条验收 + 写表。发现的条目没有价格/配率，只写新盘主表。"""
    run.stage("accepting")
    page_cache: dict = {}
    records: list[dict] = []
    offset = len(run.state.get("items") or [])

    render = page_renderer(run.dir / "feeds")

    for index, candidate in enumerate(candidates):
        # 品牌按赏盘名前缀定，不按渠道：同一个微博号会发多个品牌的盘
        candidate["brand"] = accept.derive_brand(
            str(candidate.get("name") or candidate.get("pan") or ""),
            str(candidate.get("brand") or ""),
        )
        candidate["name"] = accept.display_name(
            str(candidate.get("name") or candidate.get("pan") or ""), candidate["brand"],
        )
        verdict = accept.verify_discover(candidate, existing, page_cache, snapshots, render=render)
        if verdict["status"] == "accepted":
            # 收藏卡 / 典藏包这类边界品：用户已确认「算」，但没确认过的类型先停下来问人
            if products.classify(candidate["name"], str(candidate.get("quote") or "")) == "confirm":
                verdict = {
                    "status": "pending_review",
                    "reasons": ["product_type_confirm"],
                    "evidence": verdict.get("evidence") or "",
                }
        record = {
            "id": f"d-{offset + index + 1}",
            "pan": str(candidate.get("name") or candidate.get("pan") or ""),
            "brand": str(candidate.get("brand") or ""),
            "gap": "new",
            "status": verdict["status"],
            "reasons": verdict["reasons"],
            "evidence": verdict.get("evidence") or "",
            "written": False,
            "candidate": candidate,
        }
        records.append(record)
        run.add_item(record)
        run.bump({"accepted": "accepted", "rejected": "rejected"}.get(verdict["status"], "pending"))
        if verdict["status"] == "accepted":
            # 同一轮里各分组会重复报同一盘：先接受的占位，后面的按重复判掉
            existing.add(accept.pan_key(record["pan"], record["brand"]))

    run.stage("writing")
    rows = [
        {"values": table.pan_values_for_new(record["candidate"])}
        for record in records
        if record["status"] == "accepted"
    ]
    if write and rows:
        table.add_pans(rows)
        for record in records:
            if record["status"] == "accepted":
                record["written"] = True
        run.bump("written", len(rows))
        run.event("write", target="new_pans", count=len(rows))
    run.save()
    return records


def resume(run_id: str, write: bool) -> int:
    """回收超时 job 的结果并重跑验收（不重新派 Agent）。"""
    run_dir = RUNS_DIR / run_id
    path = run_dir / "run.json"
    if not path.exists():
        print(json.dumps({"error": f"没有这条运行：{run_id}"}, ensure_ascii=False))
        return 1
    state = json.loads(path.read_text(encoding="utf-8"))
    run = Run(state.get("kind") or "discover", trigger="resume", dry_run=not write, run_id=run_id)
    run.state = state
    run.state["status"] = "running"
    run.state["stage"] = "resuming"
    run.state["resumedAt"] = now_iso()
    run.save()

    jobs = state.get("jobs") or []
    if not jobs and (state.get("params") or {}).get("jobId"):
        jobs = [{"jobId": state["params"]["jobId"], "group": "legacy"}]
    if not jobs:
        run.finish("failed", "这条运行没有记 jobId，回收不了")
        return 1

    items, captured, feed_errors, ds_hits = load_feeds(run_dir)
    run.state["feeds"] = {
        "items": len(items),
        "channels": len(captured),
        "errors": len(feed_errors),
        "ds": (run.state.get("feeds") or {}).get("ds") or {"hits": len(ds_hits)},
    }
    run.save()
    snapshots = feeds.snapshot_index(items)
    texts = []
    timeouts = 0
    for job in jobs:
        snapshot = dispatch.fetch_job(job.get("jobId") or "")
        text = str(snapshot.get("text") or "")
        job["status"] = str(snapshot.get("status") or "unknown")
        job["chars"] = len(text)
        if job["status"] == "timeout":
            timeouts += 1
        texts.append(text)
    run.state["jobs"] = jobs
    (run_dir / "candidates.json").write_text(
        json.dumps({"jobs": jobs, "texts": texts, "resumed": True}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    existing_pans = table.load_pans()
    existing = {accept.pan_key(pan["name"], pan["brand"]) for pan in existing_pans}
    already = {
        norm(item.get("pan") or "")
        for item in state.get("items") or []
        if item.get("status") == "accepted"
    }
    candidates = []
    seen_names: set[str] = set()
    for text in texts:
        for candidate in dispatch.parse_candidates(text):
            name = norm(str(candidate.get("name") or candidate.get("pan") or ""))
            if not name or name in seen_names or name in already:
                continue
            seen_names.add(name)
            candidates.append(candidate)
    run.event("resume_candidates", count=len(candidates))
    run.bump("done")

    accept_and_write(run, candidates, existing, snapshots, write)

    answered = sum(1 for text in texts if text.strip())
    run.state["answer"] = {"groups": len(jobs), "answered": answered, "timeouts": timeouts}
    run.save()
    if answered < len(jobs):
        run.finish("partial", f"仍有 {len(jobs) - answered}/{len(jobs)} 组没有结果")
    else:
        run.finish("done")
    log(f"回收完成：候选 {len(candidates)}，写入 {run.state['counts']['written']}")
    return 0


def reaccept(run_id: str, write: bool) -> int:
    """不重新派 Agent，用已保存的 candidates.json 重跑验收（调匹配规则/口径时用）。"""
    from acg.common import RUNS_DIR, now_iso, save_state

    state_path = RUNS_DIR / run_id / "run.json"
    if state_path.exists():
        try:
            saved = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            saved = {}
        if saved.get("kind") == "discover":
            return reaccept_discover(run_id, saved, write)

    run_dir = RUNS_DIR / run_id
    state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    decided = [item for item in state.get("items") or [] if item.get("decidedBy") == "human"]
    if decided:
        print(json.dumps({
            "error": f"这条运行有 {len(decided)} 条人工裁决，重跑验收会把它们冲掉；要重验请另起一轮",
        }, ensure_ascii=False))
        return 1
    batch = state.get("batch") or []
    if not batch:
        # 旧 run 没存 batch：用当前缺口回填同 record_id 的条目
        wanted = {item.get("panRecordId") for item in state.get("items", []) if item.get("panRecordId")}
        try:
            current = gaps.compute(table.load_pans(), table.load_subs())["byPan"]
            batch = [item for rid, item in current.items() if rid in wanted]
        except Exception:  # noqa: BLE001
            batch = []
    candidates_path = run_dir / "candidates.json"
    text = ""
    texts: list[str] = []
    if candidates_path.exists():
        saved = json.loads(candidates_path.read_text(encoding="utf-8"))
        text = saved.get("text") or ""
        texts = [piece for piece in (saved.get("texts") or []) if isinstance(piece, str) and piece.strip()]
    # 现在一轮会派多个 job，「text」是拼起来的；逐块解析才不会只吃到第一块
    candidates: list[dict] = []
    for piece in texts or [text]:
        candidates.extend(dispatch.parse_candidates(piece))
    if candidates_path.exists():
        saved = json.loads(candidates_path.read_text(encoding="utf-8"))
        for lane_name in ("deepseek", "social"):
            block = saved.get(lane_name) or {}
            for row in block.get("items") or []:
                if isinstance(row, dict):
                    candidates.append(dict(row))
    page_cache: dict = {}
    render = page_renderer(run_dir / "feeds")
    ocr = ocr_reader(run_dir / "ocr")
    records = []
    for item in batch:
        candidate = accept.match_candidate(item, candidates)
        records.append(accept.verify_item(item, candidate, page_cache, render, ocr))

    counts = {"dispatched": state.get("counts", {}).get("dispatched", 0), "done": 1,
              "accepted": 0, "rejected": 0, "pending": 0, "unavailable": 0, "written": 0}
    for record in records:
        key = {"accepted": "accepted", "rejected": "rejected", "pending_review": "pending"}.get(
            record["status"], "unavailable")
        counts[key] += 1
    plan = build_write_plan(records, batch)
    if write and plan["price"]:
        table.update_pans(plan["price"])
        counts["written"] += len(plan["price"])
    if write:
        for index in range(0, len(plan["counts"]), 10):
            chunk = plan["counts"][index : index + 10]
            table.update_subs(chunk)
            counts["written"] += len(chunk)
        if plan.get("subs"):
            table.add_subs(plan["subs"])
            counts["written"] += len(plan["subs"])

    state["batch"] = batch
    state["items"] = records
    state["counts"] = counts
    state["status"] = "done"
    state["stage"] = "done"
    state["endedAt"] = now_iso()
    state["reacceptedAt"] = now_iso()
    save_state(run_dir / "run.json", state)
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": now_iso(), "type": "reaccept", "counts": counts,
                                 "writePlan": {"price": len(plan["price"]), "counts": len(plan["counts"]),
                                               "subs": len(plan.get("subs") or [])}},
                                ensure_ascii=False) + "\n")
    print(json.dumps({"run": run_id, "counts": counts, "items": records}, ensure_ascii=False, indent=1))
    return 0


def reaccept_discover(run_id: str, state: dict, write: bool) -> int:
    """用 discover 已保存的 Agent 原文重跑验收：改了去重/品牌/来源规则后不必再等一轮 Agent。"""
    from acg.common import RUNS_DIR

    if (state.get("counts") or {}).get("written"):
        print(json.dumps({"error": "这条运行已经写过表，重跑验收会重复建行；请直接重跑 discover"},
                         ensure_ascii=False))
        return 1
    run_dir = RUNS_DIR / run_id
    candidates_path = run_dir / "candidates.json"
    if not candidates_path.exists():
        print(json.dumps({"error": f"{run_id} 没有 candidates.json，回收不了"}, ensure_ascii=False))
        return 1
    payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    texts = payload.get("texts") or ([payload["text"]] if payload.get("text") else [])
    if not texts:
        print(json.dumps({"error": "candidates.json 里没有 Agent 原文"}, ensure_ascii=False))
        return 1

    items, captured, feed_errors, _ds_hits = load_feeds(run_dir)
    snapshots = feeds.snapshot_index(items)
    candidates = []
    seen: set[str] = set()
    for text in texts:
        for candidate in dispatch.parse_candidates(text):
            name = str(candidate.get("name") or candidate.get("pan") or "")
            key = accept.pan_key(name, str(candidate.get("brand") or ""))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
    # DeepSeek 通道的候选也存了，重跑验收要一起算，否则只验 workbuddy 那一路
    for candidate in ((payload.get("deepseek") or {}).get("items") or []):
        if not isinstance(candidate, dict):
            continue
        name = str(candidate.get("name") or candidate.get("pan") or "")
        key = accept.pan_key(name, str(candidate.get("brand") or ""))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)

    run = Run("discover", trigger="reaccept", dry_run=not write, run_id=run_id)
    run.state = state
    run.state["items"] = []  # 没用 --write 之前一切可重算
    for key in ("accepted", "rejected", "pending", "unavailable"):
        run.state["counts"][key] = 0
    run.state["stage"] = "accepting"
    run.state["status"] = "running"
    run.state["reacceptedAt"] = now_iso()
    run.save()

    existing_pans = table.load_pans()
    existing = {accept.pan_key(pan["name"], pan["brand"]) for pan in existing_pans}
    accept_and_write(run, candidates, existing, snapshots, write)
    answered = sum(1 for text in texts if str(text).strip())
    run.state["answer"] = {"groups": state.get("answer", {}).get("groups") or len(texts),
                           "answered": answered, "timeouts": 0}
    run.save()
    run.finish("done", None)
    log(f"重跑验收：候选 {len(candidates)}，写入 {run.state['counts']['written']}")
    return 0


def reclassify(run_id: str, write: bool) -> int:
    """按当前口径重新归类一条已有运行（离线：不联网、不重派 Agent、默认不写表）。

    只动「还没人裁过」的条目，人工裁决过的保持原样；重判后仍会按需重建写表计划，
    但只有 --write 才真的写，避免历史运行被动改表。
    """
    from acg.common import RUNS_DIR, now_iso

    run_dir = RUNS_DIR / run_id
    path = run_dir / "run.json"
    if not path.exists():
        print(json.dumps({"error": f"没有这条运行：{run_id}"}, ensure_ascii=False))
        return 1
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("kind") != "backfill":
        print(json.dumps({"error": "只有补齐（backfill）能重判归类；抓新品请用 --reaccept"}, ensure_ascii=False))
        return 1

    batch = state.get("batch") or []
    by_id = {item.get("panRecordId"): item for item in batch}
    if not batch:
        print(json.dumps({"error": "这条运行没有存批次，重判不了"}, ensure_ascii=False))
        return 1

    counts = {"dispatched": state.get("counts", {}).get("dispatched", 0),
              "done": state.get("counts", {}).get("done", 0),
              "accepted": 0, "rejected": 0, "pending": 0, "unavailable": 0,
              "written": state.get("counts", {}).get("written", 0)}
    changed = []
    for record in state.get("items") or []:
        entry = by_id.get(record.get("panRecordId")) or {}
        gaps = entry.get("gaps") or ([record["gap"]] if record.get("gap") else [])
        before = record.get("status")
        accept.restatus(record, list(gaps))
        if record.get("status") != before:
            changed.append({"pan": record.get("pan"), "from": before, "to": record["status"]})
        key = {"accepted": "accepted", "rejected": "rejected", "pending_review": "pending"}.get(
            record.get("status"), "unavailable")
        counts[key] += 1

    state["counts"] = counts
    state["reclassifiedAt"] = now_iso()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

    plan: dict = {"price": [], "counts": []}
    if write:
        records = state.get("items") or []
        plan = build_write_plan(records, batch)
        if plan["price"]:
            table.update_pans(plan["price"])
        for index in range(0, len(plan["counts"]), 10):
            table.update_subs(plan["counts"][index : index + 10])
        state["counts"]["written"] = state["counts"].get("written", 0) + len(plan["price"]) + len(plan["counts"])
        path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": now_iso(), "type": "reclassify", "changed": changed,
                                 "counts": counts, "dryRun": not write}, ensure_ascii=False) + "\n")
    print(json.dumps({"run": run_id, "changed": changed, "counts": counts,
                      "writePlan": {"price": len(plan["price"]), "counts": len(plan["counts"])},
                      "dryRun": not write}, ensure_ascii=False, indent=1))
    return 0


def decide(run_id: str, item_id: str, decision: str, note: str, source: str, dry: bool) -> int:
    """人工裁决入口：整段读改写都在跨进程锁里，避免同时点多个「采信」互相覆盖。"""
    from acg.common import RUNS_DIR, run_lock

    run_dir = RUNS_DIR / run_id
    with run_lock(run_dir):
        return _decide_locked(run_dir, item_id, decision, note, source, dry)


def _decide_locked(run_dir, item_id: str, decision: str, note: str, source: str, dry: bool) -> int:
    from acg.common import now_iso, save_state

    state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    items = state.get("items") or []
    item = next((x for x in items if x.get("id") == item_id), None)
    if not item:
        print(json.dumps({"error": f"没有条目 {item_id}"}, ensure_ascii=False))
        return 1
    if item.get("status") not in ("pending_review", "unavailable"):
        print(json.dumps({"error": f"条目状态是 {item.get('status')}，只有待确认 / 未公布才能裁决"}, ensure_ascii=False))
        return 1
    # 裁决前记下原状态，统计里要把它从对应的桶里扣掉
    previous = item.get("status")

    batch = state.get("batch") or []
    entry = next((x for x in batch if x.get("panRecordId") == item.get("panRecordId")), None)
    written = {"price": 0, "counts": 0, "pans": 0, "subs": 0}
    planned = {"price": 0, "counts": 0, "pans": 0, "subs": 0}

    candidate = item.get("candidate") or {}
    # 抓新品的条目没有「缺口」：采信 = 把这条候选建进主表（和自动采信走同一个字段映射）
    discover = state.get("kind") == "discover"

    if decision == "accept" and discover:
        if not (candidate.get("name") or candidate.get("pan")):
            print(json.dumps({"error": "这条候选没有盘名，建不了行；请判废"}, ensure_ascii=False))
            return 1
        if not dry:
            table.add_pans([{"values": table.pan_values_for_new(candidate)}])
            written["pans"] = 1
        planned["pans"] = 1
        item["status"] = "accepted"
        item["written"] = not dry
        item["decidedBy"] = "human"
        item["decidedAt"] = now_iso()
        item["ask"] = ""
        if previous == "pending_review":
            state["counts"]["pending"] = max(0, state["counts"].get("pending", 0) - 1)
        else:
            state["counts"]["unavailable"] = max(0, state["counts"].get("unavailable", 0) - 1)
        state["counts"]["accepted"] = state["counts"].get("accepted", 0) + 1
        state["counts"]["written"] = state["counts"].get("written", 0) + written["pans"]
    elif decision == "accept":
        if not entry:
            print(json.dumps({"error": "这条盘在表里找不到对应的行（批次已失效），采信写不进去"}, ensure_ascii=False))
            return 1
        # 只写这条的缺口字段：人担保的是「这个缺口」，不是「顺手把别的列也改了」
        plan = accept.plan_manual_write({**item, "gaps": entry.get("gaps") or []}, entry, candidate)
        price_rows = []
        count_rows = []
        if plan["price"]:
            price = plan["price"]
            price_rows.append({
                "record_id": price["record_id"],
                "values": {"单抽价": cell_text(table.price_cell(price["value"], price["currency"], price["currency"] == "JPY"))},
            })
        for prize in plan["counts"]:
            count_rows.append({"record_id": prize["record_id"], "values": {"单套数量": int(prize["count"])}})
        sub_rows = [
            {"values": table.sub_values_for_new(row["pan_record_id"], row["pan_name"], row)}
            for row in plan["subs"]
        ]
        planned = {"price": len(price_rows), "counts": len(count_rows), "subs": len(sub_rows)}
        if not price_rows and not count_rows and not sub_rows:
            # 以前这里会退回去写「别的字段」，于是条目变「已采信」但缺的那个数仍是空 —— 假成功
            lacks = "、".join(accept.FIELD_LABEL.get(field, field) for field in plan["missing"]) or "缺口"
            print(json.dumps({
                "error": f"这条缺的是{lacks}，但候选里没有能写进表的{lacks}（来源没公布），采信写不进任何东西。"
                         f"请判废，或等来源更新后重跑一轮。",
            }, ensure_ascii=False))
            return 1
        if not dry:
            if price_rows:
                table.update_pans(price_rows)
                written["price"] = len(price_rows)
            for index in range(0, len(count_rows), 10):
                chunk = count_rows[index : index + 10]
                table.update_subs(chunk)
                written["counts"] += len(chunk)
            if sub_rows:
                table.add_subs(sub_rows)
                written["subs"] = len(sub_rows)
        item["status"] = "accepted"
        item["decidedBy"] = "human"
        item["decidedAt"] = now_iso()
        item["manualSource"] = source
        # 人工采信后这条缺口已经有归属：记下是哪几项，别再让前端按旧 reasons 显示「机器核不了」。
        # dry-run 只算不写，所以这里按「计划写的字段」记，不按实际写入条数。
        item["wroteFields"] = [
            name for name, rows in (("price", plan["price"]), ("count", plan["counts"]), ("sub", plan["subs"])) if rows
        ]
        item["ask"] = ""
        if previous == "pending_review":
            state["counts"]["pending"] = max(0, state["counts"].get("pending", 0) - 1)
        else:
            state["counts"]["unavailable"] = max(0, state["counts"].get("unavailable", 0) - 1)
        state["counts"]["accepted"] = state["counts"].get("accepted", 0) + 1
        state["counts"]["written"] = (
            state["counts"].get("written", 0) + written["price"] + written["counts"] + written["subs"]
        )
    else:
        item["status"] = "rejected"
        item["reasons"] = list(item.get("reasons") or []) + ["manual_reject"]
        item["decidedBy"] = "human"
        item["decidedAt"] = now_iso()
        if previous == "pending_review":
            state["counts"]["pending"] = max(0, state["counts"].get("pending", 0) - 1)
        else:
            state["counts"]["unavailable"] = max(0, state["counts"].get("unavailable", 0) - 1)
        state["counts"]["rejected"] = state["counts"].get("rejected", 0) + 1

    if note:
        item["note"] = note
    if source:
        item["manualSource"] = source
        item.setdefault("sources", []).append(source)
    (run_dir / "run.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": now_iso(), "type": "decide", "item": item_id,
                                 "decision": decision, "written": written, "dryRun": dry},
                                ensure_ascii=False) + "\n")
    print(json.dumps({"item": item, "written": written, "planned": planned, "dryRun": dry}, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ACG 官方赏抓取引擎")
    parser.add_argument("--kind", choices=["backfill", "discover"], default="backfill")
    parser.add_argument("--snapshot", action="store_true", help="只读输出当前缺口，不建运行")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--write", dest="write", action="store_true")
    parser.add_argument("--batch", type=int, default=999, help="本轮最多补几个盘；默认 999 = 整个缺口队列（内部按每 6 盘一个 job 切块派发）")
    parser.add_argument("--pans", default="", help="只补这些盘（盘名子串，逗号分隔；配合 --batch 控制条数）")
    parser.add_argument("--gaps", default="", help="只补这些缺口类型（sub / price / count，逗号分隔）")
    parser.add_argument(
        "--lanes",
        default="workbuddy,deepseek,social",
        help="补齐通道，逗号分隔：workbuddy（翻官方页面）/ deepseek（搜索 + 抽取）/ social（微博 + 小红书，"
        "单轮 ≤6 盘、命中风控即停并冷却）；默认三条都开，social 是补充通道",
    )
    parser.add_argument("--since", default="")
    parser.add_argument("--until", default="")
    parser.add_argument("--trigger", default="manual")
    parser.add_argument("--no-agent", action="store_true", help="只算清单，不派 Agent")
    parser.add_argument("--run-id", default="", help="指定 run id（插件侧生成）")
    parser.add_argument("--pages", type=int, default=2, help="微博时间线翻页数（每页 10 条）")
    parser.add_argument("--groups", type=int, default=1, help="[已废弃] 现在只派 1 个覆盖全品牌的 workbuddy 任务")
    parser.add_argument("--wait", type=int, default=1200, help="单轮等 Agent 的秒数上限")
    parser.add_argument("--resume", default="", help="按 run id 回收超时 job 的结果并重跑验收，不重新派 Agent")
    parser.add_argument("--reaccept", default="", help="用已有 run 的 candidates.json 重跑验收，不重新派 Agent")
    parser.add_argument("--decide", default="", help="对待确认条目做人工裁决：需要 --item 与 --decision")
    parser.add_argument("--reclassify", default="", help="按当前口径离线重判一条补齐运行（不联网、不重派）")
    parser.add_argument("--item", default="", help="条目 id（i-<panRecordId>）")
    parser.add_argument("--decision", choices=["accept", "reject"], default="", help="accept=采信并写入，reject=判废")
    parser.add_argument("--note", default="", help="裁决备注")
    parser.add_argument("--source", default="", help="人工核对的来源 URL")
    args = parser.parse_args()

    if args.decide:
        if not args.item or not args.decision:
            print(json.dumps({"error": "缺少 --item 或 --decision"}, ensure_ascii=False))
            return 1
        return decide(args.decide, args.item, args.decision, args.note, args.source, not args.write)

    if args.reclassify:
        return reclassify(args.reclassify, args.write)

    if args.resume:
        # 回收也要拿锁：同一时间只能有一个 discover 在动这批 job 与表
        kind = "discover"
        try:
            kind = json.loads((RUNS_DIR / args.resume / "run.json").read_text(encoding="utf-8")).get("kind") or kind
        except (OSError, json.JSONDecodeError):
            pass
        lock = acquire_lock(kind)
        try:
            return resume(args.resume, args.write)
        finally:
            lock.unlink(missing_ok=True)

    if args.reaccept:
        lock = acquire_lock("discover")
        try:
            return reaccept(args.reaccept, args.write)
        finally:
            lock.unlink(missing_ok=True)

    if args.snapshot:
        print(json.dumps(snapshot(), ensure_ascii=False, indent=1))
        return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 面板上的「停止」是 SIGTERM；转成 KeyboardInterrupt，落到下面的兜底里写 interrupted，
    # 否则 run.json 会永远停在 running。
    def _stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    lock = acquire_lock(args.kind)
    run = None
    try:
        if args.kind == "backfill":
            run = Run("backfill", trigger=args.trigger, dry_run=not args.write, run_id=args.run_id or None)
            lanes = [name.strip() for name in args.lanes.split(",") if name.strip()]
            pan_filters = [name.strip() for name in args.pans.split(",") if name.strip()]
            gap_filters = [name.strip() for name in args.gaps.split(",") if name.strip()]
            backfill(
                run, args.batch, not args.no_agent, args.write,
                wait=args.wait, lanes=lanes, pan_filters=pan_filters, gap_filters=gap_filters,
            )
        else:
            since = args.since
            if not since:
                from acg.common import last_success_date

                anchor = last_success_date("discover")
                base = datetime.strptime(anchor, "%Y-%m-%d") if anchor else datetime.now(TZ) - timedelta(days=4)
                since = (base - timedelta(days=1)).strftime("%Y-%m-%d")
            until = args.until or today()
            run = Run("discover", trigger=args.trigger, dry_run=not args.write, run_id=args.run_id or None)
            discover(
                run, since, until, not args.no_agent, args.write,
                pages=args.pages, wait_seconds=args.wait,
            )
        return 0 if run.state["status"] == "done" else 1
    except SystemExit:
        raise
    except KeyboardInterrupt:
        log("已手动停止")
        if run:
            run.finish("interrupted", "手动停止")
        return 130
    except Exception as error:  # noqa: BLE001 - 引擎失败必须显式落盘
        log(f"失败：{error}")
        if run:
            run.finish("failed", str(error)[:500])
        else:
            latest = latest_run()
            if latest:
                log(f"上一条运行：{latest.get('id')} {latest.get('status')}")
        return 1
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
