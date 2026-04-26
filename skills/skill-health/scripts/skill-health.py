#!/usr/bin/env python3
"""Local skill inventory and health reporting CLI.

The CLI intentionally avoids network access and destructive actions. It reads
local skill files and local host logs, normalizes them, and writes reports.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable


DEFAULT_STATE_DIR = Path.home() / ".skill-health"
DEFAULT_REVIEW_CADENCE_DAYS = 14
DEFAULT_SNOOZE_DAYS = 7
OUTCOME_SIGNALS = {
    "completed",
    "followup_fix_requested",
    "rerun_same_task",
    "abandoned",
    "explicit_positive",
    "explicit_negative",
    "unknown",
}
WEAK_DESCRIPTION_PATTERNS = (
    "helps with",
    "useful for",
    "assists with",
    "general",
)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "use",
    "used",
    "using",
    "when",
    "with",
    "尤其",
    "使用",
    "按照",
    "生成",
    "读取",
    "数据",
}


@dataclass
class Skill:
    name: str
    description: str
    path: str
    root: str
    host: str
    source: str
    modified_at: str
    trigger_terms: list[str]


@dataclass
class UsageEvent:
    skill_name: str
    scenario: str
    timestamp: str
    agent: str
    session_id: str
    outcome_signal: str
    source: str


@dataclass
class HealthFinding:
    kind: str
    severity: str
    skill_name: str
    message: str
    recommendation: str
    evidence: dict[str, object]
    finding_id: str = ""
    feedback_status: str = "none"


@dataclass
class AdapterStatus:
    host: str
    root: str
    root_status: str
    source: str
    note: str


@dataclass
class UsageImportStatus:
    agent: str
    files_checked: list[str]
    files_imported: list[str]
    files_missing: list[str]
    imported: int
    usage_available: bool


@dataclass
class FeedbackRecord:
    type: str
    finding_id: str
    verdict: str
    note: str
    ts: str


@dataclass
class ReviewState:
    cadence_days: int
    last_doctor_at: str | None
    last_feedback_at: str | None
    last_prompted_at: str | None
    dismissed_until: str | None
    last_active_findings: int


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def finding_id_for(finding: HealthFinding) -> str:
    if finding.kind == "usage_unavailable":
        return "usage_unavailable:*"
    if finding.kind == "duplicate_candidate":
        other = str(finding.evidence.get("other_skill", "unknown"))
        left, right = sorted([finding.skill_name, other])
        return f"duplicate_candidate:{left}:{right}"
    return f"{finding.kind}:{finding.skill_name}"


def attach_finding_ids(findings: list[HealthFinding]) -> list[HealthFinding]:
    for finding in findings:
        finding.finding_id = finding_id_for(finding)
    return findings
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def iso_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_state_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def tokenize(value: str) -> list[str]:
    terms = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", value.lower())
    return sorted({term for term in terms if len(term) > 1 and term not in STOPWORDS})


def source_from_path(path: Path) -> str:
    text = str(path)
    if "/.codex/" in text:
        return "codex"
    if "/.agents/" in text:
        return "agents"
    if "/.claude/" in text:
        return "claude"
    return "custom"


def discover_roots(host: str) -> list[Path]:
    home = Path.home()
    if host == "openclaw":
        return [
            home / ".agents" / "skills",
            home / "WorkBuddy" / "Claw" / "skills",
        ]
    if host == "hermes":
        return [
            home / ".codex" / "skills",
            home / ".hermes" / "skills",
            home / "Library" / "Application Support" / "Hermes" / "skills",
        ]
    return []


def adapter_statuses(roots: list[Path], host: str, explicit_roots: bool) -> list[AdapterStatus]:
    statuses: list[AdapterStatus] = []
    source = "configured" if explicit_roots else "inferred"
    for root in roots:
        statuses.append(
            AdapterStatus(
                host=host,
                root=str(root),
                root_status="available" if root.exists() else "missing",
                source=source,
                note="explicit root supplied by caller" if explicit_roots else "candidate root inferred by adapter",
            )
        )
    return statuses


def iter_skill_files(roots: Iterable[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("SKILL.md"):
            if any(part.startswith("_") for part in path.relative_to(root).parts[:-1]):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield path


def load_skill(path: Path, root: Path, host: str) -> Skill:
    text = path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(text)
    name = frontmatter.get("name") or path.parent.name
    description = frontmatter.get("description", "")
    trigger_terms = tokenize(f"{name} {description}")
    return Skill(
        name=name,
        description=description,
        path=str(path),
        root=str(root),
        host=host,
        source=source_from_path(path),
        modified_at=iso_from_mtime(path),
        trigger_terms=trigger_terms,
    )


def scan_skills(roots: list[Path], host: str) -> list[Skill]:
    skills: list[Skill] = []
    for root in roots:
        for path in iter_skill_files([root]):
            skills.append(load_skill(path, root, host))
    return sorted(skills, key=lambda skill: (skill.name, skill.path))


def read_index(state_dir: Path) -> list[Skill]:
    index_path = state_dir / "index.json"
    if not index_path.exists():
        return []
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return [Skill(**item) for item in data.get("skills", [])]


def write_index(state_dir: Path, skills: list[Skill], statuses: list[AdapterStatus]) -> None:
    ensure_state_dir(state_dir)
    payload = {
        "generated_at": utc_now(),
        "adapter_status": [asdict(status) for status in statuses],
        "skills": [asdict(skill) for skill in skills],
    }
    (state_dir / "index.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_adapter_status(state_dir: Path) -> list[dict[str, object]]:
    index_path = state_dir / "index.json"
    if not index_path.exists():
        return []
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return data.get("adapter_status", [])


def normalize_event(raw: dict[str, object], default_agent: str, source: str) -> UsageEvent:
    skill_name = str(raw.get("skill_name") or raw.get("skill") or raw.get("name") or "unknown")
    outcome = str(raw.get("outcome_signal") or raw.get("outcome") or "unknown")
    if outcome not in OUTCOME_SIGNALS:
        outcome = "unknown"
    return UsageEvent(
        skill_name=skill_name,
        scenario=str(raw.get("scenario") or raw.get("prompt") or "unknown"),
        timestamp=str(raw.get("timestamp") or raw.get("ts") or utc_now()),
        agent=str(raw.get("agent") or default_agent),
        session_id=str(raw.get("session_id") or raw.get("session") or "unknown"),
        outcome_signal=outcome,
        source=str(raw.get("source") or source),
    )


def import_events(event_files: list[Path], state_dir: Path, agent: str) -> UsageImportStatus:
    ensure_state_dir(state_dir)
    imported: list[UsageEvent] = []
    existing_keys = {event_key(event) for event in read_events(state_dir)}
    files_imported: list[str] = []
    files_missing: list[str] = []
    for event_file in event_files:
        if not event_file.exists():
            files_missing.append(str(event_file))
            continue
        files_imported.append(str(event_file))
        with event_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event = normalize_event(raw, agent, str(event_file))
                key = event_key(event)
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                imported.append(event)
    events_path = state_dir / "events.jsonl"
    with events_path.open("a", encoding="utf-8") as handle:
        for event in imported:
            handle.write(json.dumps(asdict(event), ensure_ascii=False, sort_keys=True) + "\n")
    return UsageImportStatus(
        agent=agent,
        files_checked=[str(path) for path in event_files],
        files_imported=files_imported,
        files_missing=files_missing,
        imported=len(imported),
        usage_available=bool(files_imported),
    )


def write_usage_status(state_dir: Path, status: UsageImportStatus) -> None:
    ensure_state_dir(state_dir)
    (state_dir / "usage-status.json").write_text(json.dumps(asdict(status), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_usage_status(state_dir: Path) -> UsageImportStatus:
    status_path = state_dir / "usage-status.json"
    if not status_path.exists():
        return UsageImportStatus(
            agent="unknown",
            files_checked=[],
            files_imported=[],
            files_missing=[],
            imported=0,
            usage_available=False,
        )
    try:
        return UsageImportStatus(**json.loads(status_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError):
        return UsageImportStatus(
            agent="unknown",
            files_checked=[],
            files_imported=[],
            files_missing=[],
            imported=0,
            usage_available=False,
        )


def append_feedback(state_dir: Path, finding_id: str, verdict: str, note: str) -> FeedbackRecord:
    ensure_state_dir(state_dir)
    record = FeedbackRecord(
        type="finding",
        finding_id=finding_id,
        verdict=verdict,
        note=note,
        ts=utc_now(),
    )
    with (state_dir / "feedback.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")
    return record


def read_feedback(state_dir: Path) -> dict[str, FeedbackRecord]:
    feedback_path = state_dir / "feedback.jsonl"
    if not feedback_path.exists():
        return {}
    latest: dict[str, FeedbackRecord] = {}
    with feedback_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                record = FeedbackRecord(**data)
            except (json.JSONDecodeError, TypeError):
                continue
            if record.type != "finding" or record.verdict not in {"confirmed", "suppressed"}:
                continue
            latest[record.finding_id] = record
    return latest


def apply_feedback(findings: list[HealthFinding], feedback: dict[str, FeedbackRecord]) -> tuple[list[HealthFinding], list[HealthFinding], int]:
    active: list[HealthFinding] = []
    suppressed: list[HealthFinding] = []
    applied = 0
    for finding in attach_finding_ids(findings):
        record = feedback.get(finding.finding_id)
        if record is None:
            active.append(finding)
            continue
        applied += 1
        finding.feedback_status = record.verdict
        finding.evidence = {
            **finding.evidence,
            "feedback_note": record.note,
            "feedback_ts": record.ts,
        }
        if record.verdict == "suppressed":
            suppressed.append(finding)
        else:
            active.append(finding)
    return active, suppressed, applied


def default_review_state() -> ReviewState:
    return ReviewState(
        cadence_days=DEFAULT_REVIEW_CADENCE_DAYS,
        last_doctor_at=None,
        last_feedback_at=None,
        last_prompted_at=None,
        dismissed_until=None,
        last_active_findings=0,
    )


def read_review_state(state_dir: Path) -> ReviewState:
    state_path = state_dir / "review-state.json"
    if not state_path.exists():
        return default_review_state()
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return ReviewState(
            cadence_days=int(data.get("cadence_days", DEFAULT_REVIEW_CADENCE_DAYS)),
            last_doctor_at=data.get("last_doctor_at"),
            last_feedback_at=data.get("last_feedback_at"),
            last_prompted_at=data.get("last_prompted_at"),
            dismissed_until=data.get("dismissed_until"),
            last_active_findings=int(data.get("last_active_findings", 0)),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return default_review_state()


def write_review_state(state_dir: Path, state: ReviewState) -> None:
    ensure_state_dir(state_dir)
    (state_dir / "review-state.json").write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_review_after_doctor(state_dir: Path, active_findings: int) -> ReviewState:
    state = read_review_state(state_dir)
    state.last_doctor_at = utc_now()
    state.last_active_findings = active_findings
    state.dismissed_until = None
    write_review_state(state_dir, state)
    return state


def review_status_payload(state_dir: Path) -> dict[str, object]:
    state = read_review_state(state_dir)
    now = datetime.now(timezone.utc)
    dismissed_until = parse_timestamp(state.dismissed_until or "")
    should_prompt = True
    reason = "never_run"
    if dismissed_until and dismissed_until > now:
        should_prompt = False
        reason = "snoozed"
    elif not state.last_doctor_at:
        should_prompt = True
        reason = "never_run"
    else:
        last_doctor = parse_timestamp(state.last_doctor_at)
        last_feedback = parse_timestamp(state.last_feedback_at or "")
        if last_feedback and last_doctor and last_feedback >= last_doctor:
            should_prompt = False
            reason = "review_completed"
        elif last_doctor and (now - last_doctor).days < state.cadence_days:
            should_prompt = False
            reason = "cadence_not_elapsed"
        else:
            should_prompt = state.last_active_findings > 0
            reason = "cadence_elapsed" if should_prompt else "no_active_findings"
    state.last_prompted_at = utc_now() if should_prompt else state.last_prompted_at
    write_review_state(state_dir, state)
    return {
        "should_prompt": should_prompt,
        "reason": reason,
        "cadence_days": state.cadence_days,
        "last_doctor_at": state.last_doctor_at,
        "last_feedback_at": state.last_feedback_at,
        "dismissed_until": state.dismissed_until,
        "last_active_findings": state.last_active_findings,
    }
    try:
        return UsageImportStatus(**json.loads(status_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError):
        return UsageImportStatus(
            agent="unknown",
            files_checked=[],
            files_imported=[],
            files_missing=[],
            imported=0,
            usage_available=False,
        )


def event_key(event: UsageEvent) -> tuple[str, str, str, str, str]:
    return (
        event.skill_name,
        event.timestamp,
        event.agent,
        event.session_id,
        event.source,
    )


def discover_event_files(agent: str) -> list[Path]:
    home = Path.home()
    if agent == "openclaw":
        return [
            home / ".agents" / "skill-usage.jsonl",
            home / ".agents" / "logs" / "skill-usage.jsonl",
        ]
    if agent == "hermes":
        return [
            home / ".hermes" / "skill_usage.jsonl",
            home / ".codex" / "skill_usage.jsonl",
        ]
    return []


def read_events(state_dir: Path) -> list[UsageEvent]:
    events_path = state_dir / "events.jsonl"
    if not events_path.exists():
        return []
    events: list[UsageEvent] = []
    with events_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(UsageEvent(**json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                continue
    return events


def latest_usage_by_skill(events: list[UsageEvent]) -> dict[str, UsageEvent]:
    latest: dict[str, UsageEvent] = {}
    for event in events:
        current = latest.get(event.skill_name)
        event_ts = parse_timestamp(event.timestamp)
        current_ts = parse_timestamp(current.timestamp) if current else None
        if current is None or (event_ts and (current_ts is None or event_ts > current_ts)):
            latest[event.skill_name] = event
    return latest


def weak_trigger(skill: Skill) -> bool:
    desc = skill.description.strip()
    desc_lower = desc.lower()
    if not desc:
        return True
    if not desc_lower.startswith("use when") and not re.match(r"^[\u4e00-\u9fff].*(使用|适用|读取|按照)", desc):
        return True
    if len(tokenize(desc)) < 4:
        return True
    return any(pattern in desc_lower for pattern in WEAK_DESCRIPTION_PATTERNS)


def overlap_score(left: Skill, right: Skill) -> float:
    name_score = SequenceMatcher(None, left.name, right.name).ratio()
    left_terms = set(left.trigger_terms)
    right_terms = set(right.trigger_terms)
    if left_terms or right_terms:
        term_score = len(left_terms & right_terms) / max(len(left_terms | right_terms), 1)
    else:
        term_score = 0.0
    description_score = SequenceMatcher(None, left.description.lower(), right.description.lower()).ratio()
    return max(name_score, term_score, description_score)


def build_findings(skills: list[Skill], events: list[UsageEvent], stale_days: int, usage_available: bool) -> list[HealthFinding]:
    findings: list[HealthFinding] = []
    latest = latest_usage_by_skill(events)
    now = datetime.now(timezone.utc)

    if not usage_available:
        findings.append(
            HealthFinding(
                kind="usage_unavailable",
                severity="medium",
                skill_name="*",
                message="Usage data unavailable because no local usage log files were imported.",
                recommendation="Configure host usage log paths or pass --events before treating unused_skill findings as real inactivity.",
                evidence={"usage_available": False},
            )
        )

    for skill in skills:
        latest_event = latest.get(skill.name)
        if latest_event is None and usage_available:
            findings.append(
                HealthFinding(
                    kind="unused_skill",
                    severity="medium",
                    skill_name=skill.name,
                    message=f"{skill.name} has no local usage events.",
                    recommendation="Review whether this skill should be kept, archived, or needs better routing.",
                    evidence={"path": skill.path, "host": skill.host},
                )
            )
        elif latest_event is not None:
            latest_ts = parse_timestamp(latest_event.timestamp)
            if latest_ts and (now - latest_ts).days >= stale_days:
                findings.append(
                    HealthFinding(
                        kind="stale_skill",
                        severity="low",
                        skill_name=skill.name,
                        message=f"{skill.name} has not been used for {(now - latest_ts).days} days.",
                        recommendation="Check whether this skill still matches current workflows before archiving.",
                        evidence={"last_used_at": latest_event.timestamp, "stale_days": stale_days},
                    )
                )

        if weak_trigger(skill):
            findings.append(
                HealthFinding(
                    kind="weak_trigger",
                    severity="high",
                    skill_name=skill.name,
                    message=f"{skill.name} has a weak or non-specific trigger description.",
                    recommendation="Rewrite description as trigger conditions, symptoms, file types, or user intents.",
                    evidence={"description": skill.description},
                )
            )

    for index, left in enumerate(skills):
        for right in skills[index + 1 :]:
            score = overlap_score(left, right)
            shared_terms = sorted(set(left.trigger_terms) & set(right.trigger_terms))
            if score >= 0.58 and shared_terms:
                findings.append(
                    HealthFinding(
                        kind="duplicate_candidate",
                        severity="medium",
                        skill_name=left.name,
                        message=f"{left.name} overlaps with {right.name}.",
                        recommendation="Manually review whether one skill should route to the other or whether triggers need sharper boundaries.",
                        evidence={
                            "other_skill": right.name,
                            "score": round(score, 3),
                            "shared_terms": shared_terms[:12],
                            "paths": [left.path, right.path],
                        },
                    )
                )

    return findings


def report_payload(
    skills: list[Skill],
    events: list[UsageEvent],
    findings: list[HealthFinding],
    usage_status: UsageImportStatus,
    adapter_status: list[dict[str, object]],
    suppressed_findings: list[HealthFinding] | None = None,
    feedback_applied: int = 0,
) -> dict[str, object]:
    suppressed_findings = suppressed_findings or []
    return {
        "generated_at": utc_now(),
        "summary": {
            "skills": len(skills),
            "usage_events": len(events),
            "findings": len(findings),
            "usage_available": usage_status.usage_available,
            "feedback_applied": feedback_applied,
            "findings_suppressed": len(suppressed_findings),
        },
        "usage_status": asdict(usage_status),
        "adapter_status": adapter_status,
        "skills": [asdict(skill) for skill in skills],
        "findings": [asdict(finding) for finding in findings],
        "suppressed_findings": [asdict(finding) for finding in suppressed_findings],
    }


def localized_message(finding: dict[str, object], language: str) -> str:
    if language == "en":
        return str(finding["message"])
    kind = str(finding["kind"])
    skill_name = str(finding["skill_name"])
    evidence = finding.get("evidence", {})
    if kind == "unused_skill":
        return f"{skill_name} 没有本地使用事件。"
    if kind == "stale_skill":
        return f"{skill_name} 已超过 {evidence.get('stale_days', '配置阈值')} 天未使用。"
    if kind == "weak_trigger":
        return f"{skill_name} 的触发描述较弱或不够具体。"
    if kind == "duplicate_candidate":
        other = evidence.get("other_skill", "另一个 skill") if isinstance(evidence, dict) else "另一个 skill"
        return f"{skill_name} 与 {other} 存在场景重叠。"
    if kind == "usage_unavailable":
        return "使用数据不可用，因为没有导入任何本地使用日志文件。"
    return str(finding["message"])


def localized_recommendation(finding: dict[str, object], language: str) -> str:
    if language == "en":
        return str(finding["recommendation"])
    kind = str(finding["kind"])
    if kind == "unused_skill":
        return "复核这个 skill 是否仍需保留、归档，或是否需要更清晰的路由入口。"
    if kind == "stale_skill":
        return "归档前先确认它是否仍匹配当前工作流。"
    if kind == "weak_trigger":
        return "把 description 改成明确的触发条件、症状、文件类型或用户意图。"
    if kind == "duplicate_candidate":
        return "人工复核两个 skill 的边界，必要时合并或重写触发描述。"
    if kind == "usage_unavailable":
        return "配置宿主使用日志路径，或通过 --events 指定日志文件，再判断 skill 是否真的未使用。"
    return str(finding["recommendation"])


def render_markdown(payload: dict[str, object], language: str = "en") -> str:
    summary = payload["summary"]
    findings = payload["findings"]
    suppressed_findings = payload.get("suppressed_findings", [])
    if language == "zh":
        title = "Skill 健康报告"
        generated_label = "生成时间"
        summary_title = "摘要"
        skills_label = "已索引 Skill"
        events_label = "使用事件"
        findings_label = "发现项"
        findings_title = "发现"
        no_findings = "没有发现问题。"
        severity_label = "严重级别"
        message_label = "说明"
        recommendation_label = "建议"
        evidence_label = "证据"
        finding_id_label = "Finding ID"
        feedback_label = "反馈状态"
        suppressed_title = "已隐藏的发现"
    else:
        title = "Skill Health Report"
        generated_label = "Generated at"
        summary_title = "Summary"
        skills_label = "Skills indexed"
        events_label = "Usage events"
        findings_label = "Findings"
        findings_title = "Findings"
        no_findings = "No findings."
        severity_label = "Severity"
        message_label = "Message"
        recommendation_label = "Recommendation"
        evidence_label = "Evidence"
        finding_id_label = "Finding ID"
        feedback_label = "Feedback status"
        suppressed_title = "Suppressed Findings"

    lines = [
        f"# {title}",
        "",
        f"{generated_label}: {payload['generated_at']}",
        "",
        f"## {summary_title}",
        "",
        f"- {skills_label}: {summary['skills']}",
        f"- {events_label}: {summary['usage_events']}",
        f"- {findings_label}: {summary['findings']}",
        "",
        f"## {findings_title}",
        "",
    ]
    if not findings:
        lines.append(no_findings)
    else:
        for finding in findings:
            lines.extend(
                [
                    f"### {finding['kind']}: {finding['skill_name']}",
                    "",
                    f"- {finding_id_label}: `{finding['finding_id']}`",
                    f"- {feedback_label}: {finding['feedback_status']}",
                    f"- {severity_label}: {finding['severity']}",
                    f"- {message_label}: {localized_message(finding, language)}",
                    f"- {recommendation_label}: {localized_recommendation(finding, language)}",
                    f"- {evidence_label}: `{json.dumps(finding['evidence'], ensure_ascii=False, sort_keys=True)}`",
                    "",
                ]
            )
    if suppressed_findings:
        lines.extend(["", f"## {suppressed_title}", ""])
        for finding in suppressed_findings:
            lines.extend(
                [
                    f"### {finding['kind']}: {finding['skill_name']}",
                    "",
                    f"- {finding_id_label}: `{finding['finding_id']}`",
                    f"- {feedback_label}: {finding['feedback_status']}",
                    f"- {message_label}: {localized_message(finding, language)}",
                    f"- {evidence_label}: `{json.dumps(finding['evidence'], ensure_ascii=False, sort_keys=True)}`",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def command_scan(args: argparse.Namespace) -> int:
    roots = [Path(root).expanduser() for root in args.root] if args.root else discover_roots(args.host)
    statuses = adapter_statuses(roots, args.host, bool(args.root))
    skills = scan_skills(roots, args.host)
    write_index(args.state_dir, skills, statuses)
    print(json.dumps({"indexed": len(skills), "state_dir": str(args.state_dir), "adapter_status": [asdict(status) for status in statuses]}, ensure_ascii=False))
    return 0


def command_import(args: argparse.Namespace) -> int:
    event_files = [Path(path).expanduser() for path in args.events] if args.events else discover_event_files(args.agent)
    status = import_events(event_files, args.state_dir, args.agent)
    write_usage_status(args.state_dir, status)
    print(json.dumps({"imported": status.imported, "state_dir": str(args.state_dir), "usage_available": status.usage_available, "files_missing": status.files_missing}, ensure_ascii=False))
    return 0


def command_report(args: argparse.Namespace) -> int:
    skills = read_index(args.state_dir)
    events = read_events(args.state_dir)
    usage_status = read_usage_status(args.state_dir)
    raw_findings = build_findings(skills, events, args.stale_days, usage_status.usage_available)
    findings, suppressed_findings, feedback_applied = apply_feedback(raw_findings, read_feedback(args.state_dir))
    payload = report_payload(
        skills,
        events,
        findings,
        usage_status,
        read_adapter_status(args.state_dir),
        suppressed_findings,
        feedback_applied,
    )
    if args.format == "md":
        sys.stdout.write(render_markdown(payload, args.language))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    roots = [Path(root).expanduser() for root in args.root] if args.root else discover_roots(args.host)
    statuses = adapter_statuses(roots, args.host, bool(args.root))
    skills = scan_skills(roots, args.host)
    write_index(args.state_dir, skills, statuses)
    event_files = [Path(path).expanduser() for path in args.events] if args.events else discover_event_files(args.agent)
    usage_status = import_events(event_files, args.state_dir, args.agent)
    write_usage_status(args.state_dir, usage_status)
    events = read_events(args.state_dir)
    raw_findings = build_findings(skills, events, args.stale_days, usage_status.usage_available)
    findings, suppressed_findings, feedback_applied = apply_feedback(raw_findings, read_feedback(args.state_dir))
    payload = report_payload(
        skills,
        events,
        findings,
        usage_status,
        [asdict(status) for status in statuses],
        suppressed_findings,
        feedback_applied,
    )
    update_review_after_doctor(args.state_dir, len(findings))

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "skill-health-report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "skill-health-report.en.md").write_text(render_markdown(payload, "en"), encoding="utf-8")
    (output_dir / "skill-health-report.zh.md").write_text(render_markdown(payload, "zh"), encoding="utf-8")
    (output_dir / "skill-health-report.md").write_text(render_markdown(payload, args.language), encoding="utf-8")
    print(json.dumps({"report_dir": str(output_dir), "findings": len(findings)}, ensure_ascii=False))
    return 0


def command_feedback(args: argparse.Namespace) -> int:
    record = append_feedback(args.state_dir, args.finding_id, args.verdict, args.note or "")
    print(json.dumps(asdict(record), ensure_ascii=False))
    return 0


def command_review_status(args: argparse.Namespace) -> int:
    print(json.dumps(review_status_payload(args.state_dir), ensure_ascii=False, indent=2))
    return 0


def command_review_snooze(args: argparse.Namespace) -> int:
    state = read_review_state(args.state_dir)
    state.dismissed_until = (datetime.now(timezone.utc) + timedelta(days=args.days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    write_review_state(args.state_dir, state)
    print(json.dumps(asdict(state), ensure_ascii=False))
    return 0


def command_review_done(args: argparse.Namespace) -> int:
    state = read_review_state(args.state_dir)
    now = utc_now()
    state.last_feedback_at = now
    state.last_prompted_at = now
    state.dismissed_until = None
    write_review_state(args.state_dir, state)
    print(json.dumps(asdict(state), ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local skill health checker for Hermes, OpenClaw, and compatible SKILL.md roots.")
    parser.add_argument("--state-dir", type=Path, default=Path(os.environ.get("SKILL_HEALTH_STATE_DIR", DEFAULT_STATE_DIR)).expanduser())
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Scan local SKILL.md roots and write index.json.")
    scan.add_argument("--root", action="append", default=[], help="Skill root to scan. May be repeated.")
    scan.add_argument("--host", choices=["custom", "openclaw", "hermes"], default="custom")
    scan.set_defaults(func=command_scan)

    import_cmd = subparsers.add_parser("import", help="Import local skill usage JSONL events.")
    import_cmd.add_argument("--agent", choices=["custom", "openclaw", "hermes"], default="custom")
    import_cmd.add_argument("--events", action="append", default=[], help="JSONL event file to import. May be repeated.")
    import_cmd.set_defaults(func=command_import)

    report = subparsers.add_parser("report", help="Generate a skill health report from local state.")
    report.add_argument("--stale-days", type=int, default=90)
    report.add_argument("--format", choices=["json", "md"], default="md")
    report.add_argument("--language", choices=["en", "zh"], default="en")
    report.set_defaults(func=command_report)

    doctor = subparsers.add_parser("doctor", help="Scan, import, and write Markdown/JSON reports.")
    doctor.add_argument("--root", action="append", default=[], help="Skill root to scan. May be repeated.")
    doctor.add_argument("--host", choices=["custom", "openclaw", "hermes"], default="custom")
    doctor.add_argument("--agent", choices=["custom", "openclaw", "hermes"], default="custom")
    doctor.add_argument("--events", action="append", default=[], help="JSONL event file to import. May be repeated.")
    doctor.add_argument("--stale-days", type=int, default=90)
    doctor.add_argument("--language", choices=["en", "zh"], default="en")
    doctor.add_argument("--output-dir", default=str(DEFAULT_STATE_DIR))
    doctor.set_defaults(func=command_doctor)

    feedback = subparsers.add_parser("feedback", help="Record local feedback for a report finding.")
    feedback.add_argument("--finding-id", required=True)
    feedback.add_argument("--verdict", choices=["confirmed", "suppressed"], required=True)
    feedback.add_argument("--note", default="")
    feedback.set_defaults(func=command_feedback)

    review_status = subparsers.add_parser("review-status", help="Check whether the agent should prompt for periodic review.")
    review_status.set_defaults(func=command_review_status)

    review_done = subparsers.add_parser("review-done", help="Mark the latest review/feedback pass as completed.")
    review_done.set_defaults(func=command_review_done)

    review_snooze = subparsers.add_parser("review-snooze", help="Snooze periodic review prompting.")
    review_snooze.add_argument("--days", type=int, default=DEFAULT_SNOOZE_DAYS)
    review_snooze.set_defaults(func=command_review_snooze)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ensure_state_dir(args.state_dir)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
