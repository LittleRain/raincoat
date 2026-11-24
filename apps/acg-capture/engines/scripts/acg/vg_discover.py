"""游戏虚拟道具首抓：发现时间窗口内新上线/新公布的游戏 → 过热度门槛 → 抓一次入库。

2026-11-18 口径调整（用户 m00840）：
- 不再维护「要追踪的游戏库」：游戏清单就是企微表里的商品行，表里出现过的游戏整游戏跳过；
- 每周只看窗口（默认 60 天）内出现的新手游/端游，过了热度门槛才抓；
- 抓一次即终态：商品入库后不再刷新价格、不再更新核验时间。
"""

from __future__ import annotations

import concurrent.futures as futures
import json
import time
from datetime import datetime, timedelta

from . import dispatch, vg_accept, vg_channels, vg_dispatch, vg_store, vg_table
from .common import CACHE_DIR, TZ, VG_LEDGER_CACHE, Run, cell_text, norm, today

WB_BATCH = 8
WB_JOB_TIMEOUT = 1200
WB_PARALLEL = 3


def _window(days: int, since: str, until: str) -> tuple[str, str]:
    until = until or today()
    if since:
        return since, until
    base = datetime.now(TZ) - timedelta(days=max(1, int(days or 60)))
    return base.strftime("%Y-%m-%d"), until


def _known_names(items: list[dict]) -> list[str]:
    """表里已有的游戏名（去重、保序）。"""
    seen: dict[str, str] = {}
    for row in items:
        name = str(row.get("game") or "").strip()
        key = norm(name)
        if key and key not in seen:
            seen[key] = name
    return list(seen.values())


def _known_targets(items: list[dict]) -> list[dict]:
    """表里已有的游戏也要每轮重抓一遍：从台账还原游戏对象（含 App Store 页，若能推出）。"""
    seen: dict[str, dict] = {}
    for row in items:
        name = str(row.get("game") or "").strip()
        key = norm(name)
        if not key:
            continue
        game = seen.setdefault(key, {"game": name, "appStore": ""})
        source = str(row.get("source") or "")
        match = __import__("re").search(r"apps\.apple\.com/[a-z]{2}/app/[^\"'\s]*id(\d+)", source)
        if match and not game["appStore"]:
            game["appStore"] = f"https://apps.apple.com/cn/app/id{match.group(1)}"
    return list(seen.values())


def _merge_targets(discovered: list[dict], known: list[dict], cap: int = 20) -> list[dict]:
    """本轮抓取目标 = 发现的热门游戏 ∪ 表里已有游戏（补老游戏的缺）。"""
    merged: dict[str, dict] = {}
    for row in discovered:
        merged[norm(row["game"])] = row
    for row in known:
        key = norm(row["game"])
        if key not in merged:
            merged[key] = {"game": row["game"], "appStore": row.get("appStore") or "", "publisher": "", "status": "已上线"}
    return list(merged.values())[:cap]


def _explicit_targets(games: list[dict]) -> list[dict]:
    """显式给定的游戏清单（初始化/补抓用）：保序去重，缺 App Store 页的现场解析。"""
    targets: list[dict] = []
    seen: set[str] = set()
    for row in games:
        name = str(row.get("game") or "").strip()
        key = norm(name)
        if not key or key in seen:
            continue
        seen.add(key)
        app_store = str(row.get("appStore") or row.get("app_store") or "").strip()
        if not app_store:
            try:
                app_store = vg_store.resolve_app_store(name)
            except Exception:  # noqa: BLE001 - 解析失败只影响 store 通道
                app_store = ""
            time.sleep(0.4)  # iTunes 搜索对连打会限流
        targets.append(
            {
                "game": name,
                "aliases": [str(x).strip() for x in (row.get("aliases") or []) if str(x).strip()],
                "publisher": str(row.get("publisher") or ""),
                "status": str(row.get("status") or "已上线"),
                "appStore": app_store,
            }
        )
    return targets


def _discover(
    run: Run, lane_set: set[str], since: str, until: str, known: list[str], cached: dict
) -> dict:
    """两源各出候选 → 合并 → 门槛过滤。返回 {raw, kept, dropped, errors}。"""
    discovery = cached["discovery"]
    thresholds = cached["thresholds"]
    raw: list[dict] = []
    errors: list[dict] = []

    wb_job = None
    if "workbuddy" in lane_set:
        prompt = vg_dispatch.workbuddy_discover_prompt(discovery, thresholds, since, until, known)
        title = f"vg-new-games-{run.id[-6:]}"
        try:
            wb_job = vg_dispatch.submit(prompt, title, run.dir / "jobs")
            run.event("discover_submit", lane="workbuddy", jobId=wb_job["jobId"])
        except Exception as error:  # noqa: BLE001 - 单 lane 失败不阻断另一条
            errors.append({"lane": "workbuddy", "id": "discover", "status": str(error)[:120]})
            run.event("discover_error", lane="workbuddy", error=str(error)[:200])

    # DeepSeek 与 workbuddy 并行：workbuddy 翻页面要 5–10 分钟，不能让 DS 干等
    pool = futures.ThreadPoolExecutor(max_workers=1)
    ds_future = None
    if "deepseek" in lane_set:
        ds_future = pool.submit(vg_dispatch.ds_discover, thresholds, discovery, known, since, until)
    try:
        if wb_job:
            final = dispatch.wait_job(wb_job["resultPath"], timeout=1200, interval=5)
            text = (final or {}).get("text") or ""
            (run.dir / f"job-{wb_job['jobId']}.txt").write_text(text, encoding="utf-8")
            found = dispatch.parse_candidates(text)
            for row in found:
                row["lane"] = "workbuddy"
            raw.extend(found)
            if (final or {}).get("status") not in ("succeeded", "done"):
                errors.append({"lane": "workbuddy", "id": "discover", "status": (final or {}).get("status")})
            run.event("discover_job", lane="workbuddy", jobId=wb_job["jobId"], candidates=len(found))

        if ds_future is not None:
            try:
                result = ds_future.result()
            except Exception as error:  # noqa: BLE001
                result = {"ok": False, "error": str(error)[:160], "items": []}
            if result.get("ok"):
                raw.extend(result.get("items") or [])
                run.event("discover_lane", lane="deepseek", candidates=len(result.get("items") or []))
            else:
                errors.append({"lane": "deepseek", "id": "discover", "status": result.get("error")})
                run.event("discover_error", lane="deepseek", error=result.get("error"))
    finally:
        pool.shutdown(wait=True)

    kept, dropped = vg_accept.filter_new_games(raw, known, thresholds)
    (run.dir / "new-games.json").write_text(
        json.dumps({"window": {"since": since, "until": until}, "kept": kept, "dropped": dropped, "raw": raw},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return {"raw": len(raw), "kept": kept, "dropped": dropped, "errors": errors}


def _capture(
    run: Run,
    games: list[dict],
    lane_set: set[str],
    since: str,
    until: str,
    cached: dict,
    wb_batch: int = 0,
    wb_timeout: int = 0,
    wb_parallel: int = 0,
) -> dict:
    """对通过门槛的新游戏抓一轮商品：store 确定性通道 + workbuddy + DeepSeek。"""
    store_candidates: list[dict] = []
    for index, game in enumerate(games):
        if not game.get("appStore"):
            continue
        if index:
            time.sleep(1.0)  # App Store 对连续请求会 429，逐个之间留间隔
        try:
            found = vg_store.collect(game)
        except Exception as error:  # noqa: BLE001 - 单游戏失败不影响其它游戏
            run.event("store_error", game=game["game"], error=str(error)[:160])
            continue
        if found.get("ok"):
            store_candidates.extend(found["items"])
            run.event("store_done", game=game["game"], items=len(found["items"]))
        else:
            run.event("store_error", game=game["game"], error=str(found.get("error"))[:160])

    wb_candidates: list[dict] = []
    lane_errors: list[dict] = []

    # DeepSeek 与 workbuddy 并行启动：workbuddy 一批要 10–25 分钟，不能让 DS 干等
    ds_pool = futures.ThreadPoolExecutor(max_workers=1)
    ds_future = None
    if "deepseek" in lane_set and games:
        ds_future = ds_pool.submit(_ds_lane, games)

    try:
        if "workbuddy" in lane_set and games:
            used = [row for row in cached["channels"] if vg_channels.usable(row)]
            size = max(1, int(wb_batch or WB_BATCH))
            batches = [games[index : index + size] for index in range(0, len(games), size)]
            batch_wb, batch_errors = _workbuddy_batches(
                run, batches, used, since, until, int(wb_timeout or WB_JOB_TIMEOUT), int(wb_parallel or WB_PARALLEL)
            )
            wb_candidates.extend(batch_wb)
            lane_errors.extend(batch_errors)

        ds_candidates: list[dict] = []
        if ds_future is not None:
            for game, result in ds_future.result():
                if not result.get("ok"):
                    lane_errors.append({"lane": "deepseek", "id": game["game"], "status": result.get("error")})
                    run.event("lane_error", lane="deepseek", game=game["game"], error=result.get("error"))
                    continue
                ds_candidates.extend(result.get("items") or [])
                run.event("lane_done", lane="deepseek", game=game["game"], candidates=len(result.get("items") or []))
    finally:
        ds_pool.shutdown(wait=True)

    (run.dir / "candidates.json").write_text(
        json.dumps({"store": store_candidates, "workbuddy": wb_candidates, "deepseek": ds_candidates},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return {"store": store_candidates, "workbuddy": wb_candidates, "deepseek": ds_candidates,
            "errors": lane_errors}


def _ds_lane(games: list[dict]) -> list[tuple[dict, dict]]:
    """DeepSeek 单通道：每个游戏 4 组查询，4 路并发。"""
    def one(game: dict) -> dict:
        return vg_dispatch.ds_products(game, 30)

    with futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, games))
    return list(zip(games, results))


def _workbuddy_batches(
    run: Run,
    batches: list[list[dict]],
    channels: list[dict],
    since: str,
    until: str,
    timeout: int,
    parallel: int,
) -> tuple[list[dict], list[dict]]:
    """workbuddy 按批并行：先把所有 batch 的 job 提交出去，再逐个等结果。

    串行时 5 批 = 时间相加；并行 3 路后墙上时间约等于 2 轮。submit 与 wait 都在
    工作线程里做，事件与状态只在主线程写，避免并发改 run.json。
    """
    def work(item: tuple[int, list[dict]]) -> dict:
        index, batch = item
        prompt = vg_dispatch.workbuddy_products_prompt(batch, channels, since, until)
        title = f"vg-all-{run.id[-6:]}-{index}"
        row = {"index": index, "games": [game["game"] for game in batch], "jobId": "", "status": "",
               "text": "", "error": ""}
        try:
            job = vg_dispatch.submit(prompt, title, run.dir / "jobs")
            row["jobId"] = job["jobId"]
            row["model"] = job.get("model")
            final = dispatch.wait_job(job["resultPath"], timeout=timeout, interval=5)
            row["status"] = (final or {}).get("status") or "unknown"
            row["text"] = (final or {}).get("text") or ""
            if not row["text"]:
                # 等超时但 job 还在后台跑：再读一次终态，别把已经跑出来的结果丢掉
                again = dispatch.wait_job(job["resultPath"], timeout=1, interval=1)
                row["text"] = (again or {}).get("text") or ""
                row["status"] = (again or {}).get("status") or row["status"]
        except Exception as error:  # noqa: BLE001 - 单批失败不影响其它批
            row["error"] = str(error)[:160]
        return row

    candidates: list[dict] = []
    errors: list[dict] = []
    workers = max(1, min(parallel, len(batches)))
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures_list = [pool.submit(work, item) for item in enumerate(batches, 1)]
        for future in futures_list:
            row = future.result()
            label = f"批次{row['index']}"
            if row["jobId"]:
                run.bump("dispatched")
                run.event("job", publisher=label, jobId=row["jobId"], lane="workbuddy",
                          model=row.get("model"), games=row["games"])
            if row["error"]:
                errors.append({"lane": "workbuddy", "id": f"batch{row['index']}", "status": row["error"]})
                run.event("job_error", publisher=label, error=row["error"])
                continue
            (run.dir / f"job-{row['jobId']}.txt").write_text(row["text"], encoding="utf-8")
            parsed = dispatch.parse_candidates(row["text"])
            for candidate in parsed:
                candidate["lane"] = "workbuddy"
            candidates.extend(parsed)
            if row["status"] not in ("succeeded", "done"):
                errors.append({"lane": "workbuddy", "id": f"batch{row['index']}", "status": row["status"]})
            run.event("job_done", publisher=label, jobId=row["jobId"], status=row["status"], candidates=len(parsed))
    return candidates, errors


def run(
    window_days: int = 0,
    lanes: str = "workbuddy,deepseek",
    since: str = "",
    until: str = "",
    write: bool = True,
    use_agent: bool = True,
    run_id: str | None = None,
    trigger: str = "manual",
    discover_only: bool = False,
    games: list[dict] | None = None,
    wb_batch: int = 0,
    wb_timeout: int = 0,
    wb_parallel: int = 0,
    policy: str = "strict",
) -> Run:
    cached = {
        "channels": vg_channels.channels(),
        "discovery": vg_channels.discovery(),
        "thresholds": vg_channels.thresholds(),
    }
    days = int(window_days or cached["thresholds"].get("windowDays") or 60)
    since, until = _window(days, since, until)
    lane_set = {x.strip() for x in lanes.split(",") if x.strip()} & {"workbuddy", "deepseek"}
    if not use_agent:
        lane_set = set()

    run = Run("vg-discover", trigger=trigger, dry_run=not write, run_id=run_id)
    run.state["params"].update(
        {"windowDays": days, "since": since, "until": until, "lanes": sorted(lane_set),
         "discoverOnly": discover_only, "policy": policy}
    )
    run.save()

    # ---- 0) 读表：表里的游戏就是「已抓到的 list」，也是发现层的排除集 ----------
    try:
        existing = vg_table.list_items()
    except Exception as error:  # noqa: BLE001 - 读不到表就没法避开已入库游戏
        run.event("ledger_error", error=str(error)[:200])
        run.finish("failed", f"读不到游戏虚拟商品表：{error}")
        return run
    known = _known_names(existing)
    if write:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            VG_LEDGER_CACHE.write_text(
                json.dumps({"at": today(), "items": existing}, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except OSError:
            pass

    run.set_table(window=days, knownGames=len(known), rows=len(existing), lanes=len(lane_set))
    run.state["scope"] = {"window": {"since": since, "until": until}, "lanes": sorted(lane_set),
                          "knownGames": len(known)}
    run.event("window", since=since, until=until, known=len(known), rows=len(existing))

    # ---- 1) 发现窗口内的新游戏（给了显式清单就跳过发现层）------------------
    explicit = bool(games)
    if explicit:
        targets = _explicit_targets(games or [])
        found = {"raw": 0, "kept": [], "dropped": [], "errors": []}
        run.event("explicit_targets", games=len(targets),
                  withAppStore=sum(1 for row in targets if row.get("appStore")))
    else:
        run.stage("discovering")
        try:
            found = _discover(run, lane_set, since, until, known, cached)
        except Exception as error:  # noqa: BLE001
            found = {"raw": 0, "kept": [], "dropped": [], "errors": [{"lane": "discover", "id": "all", "status": str(error)[:160]}]}
            run.event("discover_error", lane="discover", error=str(error)[:200])
    run.state["discovery"] = {
        "raw": found["raw"],
        "kept": len(found["kept"]),
        "dropped": len(found["dropped"]),
        "errors": found["errors"],
        "games": [
            {"game": row["game"], "publisher": row.get("publisher"), "priority": row.get("priority"),
             "heat": row.get("heat") or [], "appStore": row.get("appStore") or "", "status": row.get("status")}
            for row in found["kept"]
        ],
        "droppedGames": [
            {"game": row.get("game"), "reason": row.get("reason")} for row in found["dropped"][:50]
        ],
    }
    run.save()

    if discover_only:
        run.finish("partial" if found["errors"] else "done",
                   "发现 lane 失败" if found["errors"] else None)
        return run

    if not explicit:
        # 每轮都要覆盖表里已有的游戏（补老游戏的缺），与发现的热门游戏合并
        targets = _merge_targets(found["kept"], _known_targets(existing))
    if not targets:
        run.stage("done")
        run.finish("done", None)
        return run
    run.state["targets"] = [row["game"] for row in targets]
    run.save()

    # ---- 2) 抓取：热门游戏 + 老游戏补缺，一次抓完 -------------------------
    batch_games = [_as_game(row) for row in targets]
    run.stage("dispatch")
    feeds = _capture(
        run, batch_games, lane_set, since, until, cached,
        wb_batch=wb_batch, wb_timeout=wb_timeout, wb_parallel=wb_parallel,
    )
    run.state["feeds"] = {
        "store": len(feeds["store"]),
        "workbuddy": len(feeds["workbuddy"]),
        "deepseek": len(feeds["deepseek"]),
        "errors": len(feeds["errors"]),
    }
    run.save()
    run.event("feeds", **run.state["feeds"])

    # ---- 3) 合并 + 验收 ---------------------------------------------------
    run.stage("accepting")
    normalized: list[dict] = []
    for candidate in feeds["store"] + feeds["workbuddy"] + feeds["deepseek"]:
        game = _match_game(candidate, batch_games)
        if game is None:
            run.event("orphan_candidate", game=candidate.get("game"), name=candidate.get("name"))
            continue
        normalized.append(vg_accept.normalize_candidate(candidate, game, str(candidate.get("lane") or "deepseek")))
    merged = vg_accept.merge(normalized)
    run.event("merged", raw=len(normalized), merged=len(merged))

    existing_keys = {vg_accept.product_key(row) for row in existing}
    page_cache: dict = {}
    verified: list[dict] = []
    for candidate in merged:
        game = _match_game(candidate, batch_games)
        if game is None:
            continue
        verified.append(vg_accept.verify(candidate, game, cached["channels"], page_cache, policy=policy))

    # 一个商品名一行：同商品不同面额的价格合并进备注，再去重判断是否补行
    products = vg_accept.combine_products(verified)
    for product in products:
        if vg_accept.product_key(product) in existing_keys:
            product["status"] = "duplicate"
            product["reasons"] = list(product.get("reasons") or []) + ["duplicate"]
            product["written"] = False
        run.add_item(product)
        run.bump(product["status"].replace("pending_review", "pending"))

    # ---- 4) 写表：只补缺的行，不更新已有行 ---------------------------------
    run.stage("writing")
    accepted = [record for record in products if record["status"] == "accepted"]
    if write and accepted:
        rows = [{"values": vg_table.item_values(record)} for record in accepted]
        vg_table.add_items(rows, vg_table.empty_records())
        for record in accepted:
            record["written"] = True
        run.bump("written", len(rows))
        run.save()
        run.event("write", target="game_virtual_goods", added=len(rows))

    errors = list(found["errors"]) + list(feeds["errors"])
    run.stage("done")
    run.finish("done" if not errors else "partial", None if not errors else "部分 lane 失败")
    return run


def _as_game(row: dict) -> dict:
    """发现候选 → 抓取层要的游戏对象（不再落库，只在本次运行里用）。"""
    return {
        "id": vg_accept_key(row["game"]),
        "game": row["game"],
        "aliases": list(row.get("aliases") or []),
        "publisher": row.get("publisher") or "",
        "status": row.get("status") or "已上线",
        "platform": row.get("platform") or "",
        "license": row.get("license") or "",
        "currency": row.get("currency") or "",
        "skuHints": [],
        "appStore": row.get("appStore") or "",
        "channelIds": [],
    }


def vg_accept_key(value: str) -> str:
    return norm(value)[:18] or "x"


def _match_game(candidate: dict, games: list[dict]) -> dict | None:
    name = str(candidate.get("game") or candidate.get("ip") or "")
    if not name:
        return None
    key = norm(name)
    for game in games:
        target = norm(game.get("game") or "")
        if target and (target in key or key in target):
            return game
    # 系列名/IP 名与具体作品名不一致时，用清单里给的别名兜底（崩坏系列 → 崩坏：星穹铁道）
    for game in games:
        for alias in game.get("aliases") or []:
            alias_key = norm(alias)
            if alias_key and (alias_key in key or key in alias_key):
                return game
    return None
