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
DEFAULT_SCAN_SCOPE = "local_only"
HERMES_DEFAULT_HOME = Path.home() / ".hermes"
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

CATEGORY_RULES = [
    ("report", ("report", "weekly-report", "日报", "周报", "report.html", "html report")),
    ("review", ("review", "审查", "评审", "qa", "质量")),
    ("planning", ("plan", "planning", "roadmap", "方案", "规划")),
    ("browser", ("browse", "browser", "chrome", "网页", "web")),
    ("automation", ("automation", "cron", "workflow", "pipeline", "自动化")),
    ("integration", ("github", "slack", "lark", "wecom", "集成", "connector")),
    ("knowledge", ("knowledge", "memory", "search", "doc", "docs", "知识")),
]


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
    profile_name: str = ""
    profile_home: str = ""
    profile_scope: str = ""


@dataclass
class UsageEvent:
    skill_name: str
    scenario: str
    timestamp: str
    agent: str
    session_id: str
    outcome_signal: str
    source: str
    trigger_source: str
    profile_name: str = ""
    profile_home: str = ""


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
    usage_mode: str
    usage_logging_status: str
    diagnosis_code: str
    diagnosis: str
    resolved_hermes_home: str | None
    usage_log_path: str | None
    health_log_path: str | None


@dataclass
class UsageHealthEvent:
    ts: str
    code: str
    message: str
    agent: str
    source: str


@dataclass
class DashboardSkill:
    name: str
    description: str
    category: str
    category_reason: str
    host: str
    modified_at: str
    trigger_terms: list[str]
    installed_profiles: list[str]
    loaded_profiles: list[str]
    sources: list[str]
    roots: list[str]
    paths: list[str]
    copy_count: int
    findings: list[dict[str, object]]


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
    if "/.hermes/" in text:
        return "hermes"
    if "/.codex/" in text:
        return "codex"
    if "/.agents/" in text:
        return "agents"
    if "/.claude/" in text:
        return "claude"
    return "custom"


def resolve_hermes_home() -> Path:
    configured = os.environ.get("HERMES_HOME")
    if configured:
        return Path(configured).expanduser()
    return HERMES_DEFAULT_HOME


def resolve_hermes_base_home() -> Path:
    hermes_home = resolve_hermes_home()
    if hermes_home.parent.name == "profiles":
        return hermes_home.parent.parent
    return hermes_home


def hermes_profile_homes() -> list[Path]:
    base_home = resolve_hermes_base_home()
    homes = [base_home]
    profiles_dir = base_home / "profiles"
    if profiles_dir.exists():
        for child in sorted(profiles_dir.iterdir()):
            if child.is_dir():
                homes.append(child)
    return homes


def hermes_profile_name(profile_home: Path) -> str:
    base_home = resolve_hermes_base_home()
    if profile_home == base_home:
        return "default"
    return profile_home.name


def classify_skill_location(path: Path, root: Path) -> tuple[str, str, str]:
    if "/.hermes/" not in str(path):
        return "", "", "custom"
    for profile_home in hermes_profile_homes():
        skills_root = profile_home / "skills"
        if root == skills_root:
            return hermes_profile_name(profile_home), str(profile_home), "profile_local"
        if str(path).startswith(str(profile_home) + os.sep):
            return hermes_profile_name(profile_home), str(profile_home), "profile_local"
    return "", "", "external"


def expand_config_path(raw_value: str, config_path: Path) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(raw_value.strip()))
    path = Path(expanded)
    if not path.is_absolute():
        path = (config_path.parent / path).resolve()
    return path


def parse_hermes_external_dirs(hermes_home: Path) -> list[Path]:
    config_path = hermes_home / "config.yaml"
    if not config_path.exists():
        return []
    lines = config_path.read_text(encoding="utf-8").splitlines()
    external_dirs: list[Path] = []
    in_skills = False
    in_external = False
    skills_indent = -1
    external_indent = -1
    for raw_line in lines:
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if stripped == "skills:":
            in_skills = True
            in_external = False
            skills_indent = indent
            external_indent = -1
            continue
        if in_skills and indent <= skills_indent:
            in_skills = False
            in_external = False
        if in_skills and stripped == "external_dirs:":
            in_external = True
            external_indent = indent
            continue
        if in_external and indent <= external_indent:
            in_external = False
        if in_external and stripped.startswith("- "):
            external_dirs.append(expand_config_path(stripped[2:], config_path))
    return external_dirs


def discover_roots(host: str, scan_scope: str = DEFAULT_SCAN_SCOPE) -> tuple[list[Path], dict[str, object]]:
    home = Path.home()
    if host == "openclaw":
        roots = [
            home / ".agents" / "skills",
            home / "WorkBuddy" / "Claw" / "skills",
        ]
        return roots, {
            "resolved_hermes_home": None,
            "effective_roots": [str(root) for root in roots],
            "scan_scope": scan_scope,
        }
    if host == "hermes":
        hermes_home = resolve_hermes_home()
        roots = [hermes_home / "skills"]
        if scan_scope == "local_plus_external":
            roots.extend(parse_hermes_external_dirs(hermes_home))
        deduped: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root.resolve()) if root.exists() else str(root)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(root)
        return deduped, {
            "resolved_hermes_home": str(hermes_home),
            "effective_roots": [str(root) for root in deduped],
            "scan_scope": scan_scope,
        }
    return [], {
        "resolved_hermes_home": None,
        "effective_roots": [],
        "scan_scope": scan_scope,
    }


def discover_dashboard_roots(host: str, scan_scope: str = DEFAULT_SCAN_SCOPE) -> tuple[list[Path], dict[str, object]]:
    if host != "hermes":
        return discover_roots(host, scan_scope)
    base_home = resolve_hermes_base_home()
    homes = hermes_profile_homes()
    roots: list[Path] = []
    for profile_home in homes:
        roots.append(profile_home / "skills")
        if scan_scope == "local_plus_external":
            roots.extend(parse_hermes_external_dirs(profile_home))
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped, {
        "resolved_hermes_home": str(resolve_hermes_home()),
        "resolved_hermes_base_home": str(base_home),
        "effective_roots": [str(root) for root in deduped],
        "scan_scope": scan_scope,
        "profile_homes": [str(home) for home in homes],
    }


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
    profile_name = ""
    profile_home = ""
    profile_scope = ""
    if host == "hermes":
        profile_name, profile_home, profile_scope = classify_skill_location(path, root)
    return Skill(
        name=name,
        description=description,
        path=str(path),
        root=str(root),
        host=host,
        source=source_from_path(path),
        modified_at=iso_from_mtime(path),
        trigger_terms=trigger_terms,
        profile_name=profile_name,
        profile_home=profile_home,
        profile_scope=profile_scope,
    )


def infer_category(skill: Skill) -> tuple[str, str]:
    haystack = " ".join(
        [
            skill.name.lower(),
            skill.description.lower(),
            skill.path.lower(),
            " ".join(skill.trigger_terms).lower(),
        ]
    )
    for category, keywords in CATEGORY_RULES:
        for keyword in keywords:
            if keyword.lower() in haystack:
                return category, f"matched keyword '{keyword}'"
    return "general", "no category rule matched"


def infer_scope(skill: Skill, scan_context: dict[str, object]) -> str:
    if skill.host != "hermes":
        return "custom"
    if skill.profile_scope:
        return skill.profile_scope
    return "external"


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


def write_index_with_context(state_dir: Path, skills: list[Skill], statuses: list[AdapterStatus], context: dict[str, object]) -> None:
    ensure_state_dir(state_dir)
    payload = {
        "generated_at": utc_now(),
        "adapter_status": [asdict(status) for status in statuses],
        "scan_context": context,
        "skills": [asdict(skill) for skill in skills],
    }
    (state_dir / "index.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_adapter_status(state_dir: Path) -> list[dict[str, object]]:
    index_path = state_dir / "index.json"
    if not index_path.exists():
        return []
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return data.get("adapter_status", [])


def read_scan_context(state_dir: Path) -> dict[str, object]:
    index_path = state_dir / "index.json"
    if not index_path.exists():
        return {
            "resolved_hermes_home": None,
            "effective_roots": [],
            "scan_scope": DEFAULT_SCAN_SCOPE,
        }
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return data.get(
        "scan_context",
        {
            "resolved_hermes_home": None,
            "effective_roots": [],
            "scan_scope": DEFAULT_SCAN_SCOPE,
        },
    )


def normalize_event(raw: dict[str, object], default_agent: str, source: str) -> UsageEvent:
    skill_name = str(raw.get("skill_name") or raw.get("skill") or raw.get("name") or "unknown")
    outcome = str(raw.get("outcome_signal") or raw.get("outcome") or "unknown")
    if outcome not in OUTCOME_SIGNALS:
        outcome = "unknown"
    profile_home = str(raw.get("profile_home") or raw.get("hermes_home") or "")
    profile_name = str(raw.get("profile_name") or raw.get("profile") or "")
    if not profile_name and profile_home:
        profile_path = Path(profile_home).expanduser()
        profile_name = hermes_profile_name(profile_path)
    return UsageEvent(
        skill_name=skill_name,
        scenario=str(raw.get("scenario") or raw.get("prompt") or "unknown"),
        timestamp=str(raw.get("timestamp") or raw.get("ts") or utc_now()),
        agent=str(raw.get("agent") or default_agent),
        session_id=str(raw.get("session_id") or raw.get("session") or "unknown"),
        outcome_signal=outcome,
        source=str(raw.get("source") or source),
        trigger_source=str(raw.get("trigger_source") or raw.get("trigger") or "unknown"),
        profile_name=profile_name,
        profile_home=profile_home,
    )


def discover_health_files(agent: str) -> list[Path]:
    if agent != "hermes":
        return []
    hermes_home = resolve_hermes_home()
    return [hermes_home / "skill_usage_health.jsonl"]


def read_latest_health_event(health_files: list[Path], default_agent: str) -> UsageHealthEvent | None:
    latest: UsageHealthEvent | None = None
    latest_ts: datetime | None = None
    for health_file in health_files:
        if not health_file.exists():
            continue
        with health_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event = UsageHealthEvent(
                    ts=str(raw.get("ts") or raw.get("timestamp") or utc_now()),
                    code=str(raw.get("code") or "unknown"),
                    message=str(raw.get("message") or "Unknown Hermes skill usage health issue."),
                    agent=str(raw.get("agent") or default_agent),
                    source=str(raw.get("source") or str(health_file)),
                )
                event_ts = parse_timestamp(event.ts)
                if latest is None or (event_ts and (latest_ts is None or event_ts > latest_ts)):
                    latest = event
                    latest_ts = event_ts
    return latest


def usage_diagnosis(
    agent: str,
    event_files: list[Path],
    files_imported: list[str],
    latest_health_event: UsageHealthEvent | None,
) -> tuple[str, str, str]:
    if latest_health_event is not None:
        return (
            latest_health_event.code,
            "warning",
            latest_health_event.message,
        )
    if files_imported:
        return (
            "available",
            "available",
            "Imported explicit host-emitted skill usage events.",
        )
    if agent == "hermes":
        return (
            "no_usage_log",
            "unavailable",
            "No Hermes skill usage events were imported. Check the current HERMES_HOME, usage log path, and Hermes host warnings.",
        )
    return (
        "no_usage_log",
        "unavailable",
        "No local usage log files were imported.",
    )


def import_events(event_files: list[Path], state_dir: Path, agent: str) -> UsageImportStatus:
    ensure_state_dir(state_dir)
    imported: list[UsageEvent] = []
    existing_keys = {event_key(event) for event in read_events(state_dir)}
    files_imported: list[str] = []
    files_missing: list[str] = []
    health_files = discover_health_files(agent)
    latest_health_event = read_latest_health_event(health_files, agent)
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
    diagnosis_code, usage_logging_status, diagnosis = usage_diagnosis(agent, event_files, files_imported, latest_health_event)
    hermes_home = str(resolve_hermes_home()) if agent == "hermes" else None
    usage_log_path = str(event_files[0]) if event_files else None
    health_log_path = str(health_files[0]) if health_files else None
    return UsageImportStatus(
        agent=agent,
        files_checked=[str(path) for path in event_files],
        files_imported=files_imported,
        files_missing=files_missing,
        imported=len(imported),
        usage_available=bool(files_imported),
        usage_mode="explicit_events_only",
        usage_logging_status=usage_logging_status,
        diagnosis_code=diagnosis_code,
        diagnosis=diagnosis,
        resolved_hermes_home=hermes_home,
        usage_log_path=usage_log_path,
        health_log_path=health_log_path,
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
            usage_mode="explicit_events_only",
            usage_logging_status="unavailable",
            diagnosis_code="no_usage_status",
            diagnosis="No usage status has been recorded yet.",
            resolved_hermes_home=None,
            usage_log_path=None,
            health_log_path=None,
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
            usage_mode="explicit_events_only",
            usage_logging_status="unavailable",
            diagnosis_code="invalid_usage_status",
            diagnosis="Usage status could not be parsed.",
            resolved_hermes_home=None,
            usage_log_path=None,
            health_log_path=None,
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


def event_key(event: UsageEvent) -> tuple[str, str, str, str, str]:
    return (
        event.skill_name,
        event.timestamp,
        event.agent,
        event.session_id,
        f"{event.source}:{event.trigger_source}",
    )


def discover_event_files(agent: str) -> list[Path]:
    home = Path.home()
    if agent == "openclaw":
        return [
            home / ".agents" / "skill-usage.jsonl",
            home / ".agents" / "logs" / "skill-usage.jsonl",
        ]
    if agent == "hermes":
        hermes_home = resolve_hermes_home()
        return [hermes_home / "skill_usage.jsonl"]
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


def build_findings(skills: list[Skill], events: list[UsageEvent], stale_days: int, usage_status: UsageImportStatus) -> list[HealthFinding]:
    findings: list[HealthFinding] = []
    latest = latest_usage_by_skill(events)
    now = datetime.now(timezone.utc)

    if not usage_status.usage_available:
        findings.append(
            HealthFinding(
                kind="usage_unavailable",
                severity="medium",
                skill_name="*",
                message="Usage data unavailable because no explicit host-emitted skill usage events were imported.",
                recommendation="Check the Hermes/OpenClaw host usage hook, the resolved usage log path, and any host health warnings before treating inactivity findings as real.",
                evidence={
                    "usage_available": False,
                    "usage_mode": usage_status.usage_mode,
                    "usage_logging_status": usage_status.usage_logging_status,
                    "diagnosis_code": usage_status.diagnosis_code,
                    "diagnosis": usage_status.diagnosis,
                    "resolved_hermes_home": usage_status.resolved_hermes_home,
                    "usage_log_path": usage_status.usage_log_path,
                    "health_log_path": usage_status.health_log_path,
                    "files_checked": usage_status.files_checked,
                    "files_missing": usage_status.files_missing,
                },
            )
        )

    for skill in skills:
        latest_event = latest.get(skill.name)
        if latest_event is None and usage_status.usage_available:
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
    scan_context: dict[str, object],
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
            "usage_logging_status": usage_status.usage_logging_status,
            "feedback_applied": feedback_applied,
            "findings_suppressed": len(suppressed_findings),
        },
        "resolved_hermes_home": scan_context.get("resolved_hermes_home"),
        "effective_roots": scan_context.get("effective_roots", []),
        "scan_scope": scan_context.get("scan_scope", DEFAULT_SCAN_SCOPE),
        "usage_status": asdict(usage_status),
        "adapter_status": adapter_status,
        "skills": [asdict(skill) for skill in skills],
        "findings": [asdict(finding) for finding in findings],
        "suppressed_findings": [asdict(finding) for finding in suppressed_findings],
    }


def localized_diagnosis(code: str, message: str, language: str) -> str:
    if language == "en":
        return message
    mapping = {
        "available": "已导入宿主显式产出的 skill usage events。",
        "no_usage_log": "没有导入任何本地 usage log 文件。",
        "hook_not_enabled": "宿主已加载 skill，但 skill usage hook 未启用。",
        "log_path_missing": "宿主 skill usage 日志路径不存在。",
        "log_path_unwritable": "宿主 skill usage 日志路径不可写。",
        "session_id_missing": "宿主写 usage event 时缺少 session_id。",
        "json_write_failed": "宿主写 usage event 时 JSON 序列化或写入失败。",
    }
    return mapping.get(code, message)


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
        return localized_diagnosis(
            str(evidence.get("diagnosis_code") or "no_usage_log"),
            str(evidence.get("diagnosis") or "No local usage log files were imported."),
            language,
        )
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
        return "先检查宿主 usage hook、usage log 路径和 health warning，再判断 skill 是否真的未使用。"
    return str(finding["recommendation"])


def read_report_payload(report_json_path: Path) -> dict[str, object] | None:
    if not report_json_path.exists():
        return None
    try:
        payload = json.loads(report_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def skill_lookup(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    mapping: dict[str, list[dict[str, object]]] = {}
    for finding in payload.get("findings", []):
        skill_name = str(finding.get("skill_name") or "")
        if skill_name and skill_name != "*":
            mapping.setdefault(skill_name, []).append(finding)
        evidence = finding.get("evidence", {})
        if finding.get("kind") == "duplicate_candidate" and isinstance(evidence, dict):
            other = str(evidence.get("other_skill") or "")
            if other:
                mapping.setdefault(other, []).append(finding)
    return mapping


def loaded_profiles_by_skill(events: list[UsageEvent]) -> dict[str, list[str]]:
    profiles: dict[str, set[str]] = {}
    for event in events:
        if not event.profile_name:
            continue
        profiles.setdefault(event.skill_name, set()).add(event.profile_name)
    return {skill_name: sorted(values) for skill_name, values in profiles.items()}


def dashboard_skills(
    skills: list[Skill],
    findings_payload: dict[str, object] | None,
    scan_context: dict[str, object],
    events: list[UsageEvent],
) -> list[DashboardSkill]:
    finding_map = skill_lookup(findings_payload or {})
    loaded_profiles = loaded_profiles_by_skill(events)
    grouped: dict[str, list[Skill]] = {}
    for skill in skills:
        grouped.setdefault(skill.name, []).append(skill)

    rows: list[DashboardSkill] = []
    for name, grouped_skills in sorted(grouped.items(), key=lambda pair: pair[0]):
        primary = grouped_skills[0]
        category, category_reason = infer_category(primary)
        descriptions = [skill.description for skill in grouped_skills if skill.description]
        description = max(descriptions, key=len) if descriptions else primary.description
        roots = sorted({skill.root for skill in grouped_skills})
        paths = sorted({skill.path for skill in grouped_skills})
        sources = sorted({skill.source for skill in grouped_skills})
        installed_profiles = sorted({skill.profile_name for skill in grouped_skills if skill.profile_name})
        latest_modified = max((skill.modified_at for skill in grouped_skills), default=primary.modified_at)
        merged_terms = sorted({term for skill in grouped_skills for term in skill.trigger_terms})
        rows.append(
            DashboardSkill(
                name=name,
                description=description,
                category=category,
                category_reason=category_reason,
                host=primary.host,
                modified_at=latest_modified,
                trigger_terms=merged_terms,
                installed_profiles=installed_profiles,
                loaded_profiles=loaded_profiles.get(name, []),
                sources=sources,
                roots=roots,
                paths=paths,
                copy_count=len(grouped_skills),
                findings=finding_map.get(name, []),
            )
        )
    return rows


def summarize_counts(items: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def inventory_report_mismatch(skills: list[Skill], scan_context: dict[str, object], report_payload_data: dict[str, object] | None) -> str | None:
    if report_payload_data is None:
        return "Doctor report not found. Dashboard shows inventory only."
    inventory_roots = {str(root) for root in scan_context.get("effective_roots", [])}
    report_roots = {str(root) for root in report_payload_data.get("effective_roots", [])}
    inventory_skills = {skill.name for skill in skills}
    report_skills = {str(item.get("name")) for item in report_payload_data.get("skills", []) if isinstance(item, dict)}
    if inventory_roots != report_roots:
        return "Dashboard inventory and latest doctor report used different roots."
    if inventory_skills != report_skills:
        return "Dashboard inventory and latest doctor report contain different skill sets."
    return None


def dashboard_payload(
    skills: list[Skill],
    dashboard_rows: list[DashboardSkill],
    scan_context: dict[str, object],
    report_payload_data: dict[str, object] | None,
) -> dict[str, object]:
    summary = {
        "skills": len(dashboard_rows),
        "categories": summarize_counts([row.category for row in dashboard_rows]),
        "sources": summarize_counts([source for row in dashboard_rows for source in row.sources]),
        "roots": summarize_counts([root for row in dashboard_rows for root in row.roots]),
        "installed_profiles": summarize_counts([profile for row in dashboard_rows for profile in row.installed_profiles]),
        "loaded_profiles": summarize_counts([profile for row in dashboard_rows for profile in row.loaded_profiles]),
    }
    report_summary = report_payload_data.get("summary", {}) if report_payload_data else {}
    findings = report_payload_data.get("findings", []) if report_payload_data else []
    suppressed = report_payload_data.get("suppressed_findings", []) if report_payload_data else []
    return {
        "generated_at": utc_now(),
        "inventory_summary": summary,
        "doctor_summary": report_summary,
        "resolved_hermes_home": scan_context.get("resolved_hermes_home"),
        "resolved_hermes_base_home": scan_context.get("resolved_hermes_base_home"),
        "effective_roots": scan_context.get("effective_roots", []),
        "profile_homes": scan_context.get("profile_homes", []),
        "scan_scope": scan_context.get("scan_scope", DEFAULT_SCAN_SCOPE),
        "report_available": report_payload_data is not None,
        "mismatch_notice": inventory_report_mismatch(skills, scan_context, report_payload_data),
        "skills": [asdict(row) for row in dashboard_rows],
        "findings": findings,
        "suppressed_findings": suppressed,
    }


def render_dashboard_html(payload: dict[str, object]) -> str:
    dashboard_data = json.dumps(payload, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Hermes Skills Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fb;
      --surface: #ffffff;
      --surface-muted: #f0f3f8;
      --text: #111827;
      --text-muted: #5b6472;
      --line: #d6dce6;
      --accent: #2563eb;
      --warn: #b45309;
      --danger: #b91c1c;
      --success: #15803d;
      --chip: #eef2ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    .page {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 24px;
    }}
    .hero, .panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 16px;
    }}
    .hero h1 {{ margin: 0 0 8px; font-size: 28px; }}
    .muted {{ color: var(--text-muted); }}
    .warning {{
      background: #fff7ed;
      border: 1px solid #fdba74;
      color: var(--warn);
      border-radius: 8px;
      padding: 12px 14px;
      margin-top: 12px;
    }}
    .summary-grid, .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 16px;
    }}
    .stat {{
      background: var(--surface-muted);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .stat .label {{ color: var(--text-muted); font-size: 12px; margin-bottom: 8px; }}
    .stat .value {{ font-size: 24px; font-weight: 600; }}
    .nav {{
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }}
    .tab {{
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--text);
      border-radius: 8px;
      padding: 10px 14px;
      cursor: pointer;
    }}
    .tab.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
    .view {{ display: none; }}
    .view.active {{ display: block; }}
    .filters {{
      display: grid;
      grid-template-columns: minmax(220px, 1.4fr) repeat(5, minmax(140px, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }}
    input, select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      background: #fff;
      color: var(--text);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--surface);
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      padding: 12px 10px;
      font-size: 14px;
    }}
    th {{ color: var(--text-muted); font-weight: 600; }}
    .chips {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }}
    .chip {{
      display: inline-flex;
      align-items: center;
      padding: 3px 8px;
      border-radius: 999px;
      background: var(--chip);
      color: #3730a3;
      font-size: 12px;
      line-height: 1.2;
    }}
    .chip.warn {{ background: #fef3c7; color: #92400e; }}
    .chip.danger {{ background: #fee2e2; color: #991b1b; }}
    .finding-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      padding: 16px;
      margin-bottom: 12px;
    }}
    .finding-card h3 {{ margin: 0 0 10px; font-size: 16px; }}
    .finding-meta {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }}
    .kv {{
      display: grid;
      grid-template-columns: 140px 1fr;
      gap: 10px;
      margin-bottom: 8px;
      font-size: 14px;
    }}
    .kv .k {{ color: var(--text-muted); }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0;
      background: var(--surface-muted);
      padding: 12px;
      border-radius: 8px;
      border: 1px solid var(--line);
      font-size: 12px;
    }}
    .empty {{
      padding: 16px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      color: var(--text-muted);
      background: var(--surface);
    }}
    a.file-link {{
      color: var(--accent);
      text-decoration: none;
      word-break: break-all;
    }}
    @media (max-width: 960px) {{
      .filters {{ grid-template-columns: 1fr; }}
      .kv {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="hero">
      <h1>Hermes Skills Dashboard</h1>
      <div class="muted">Generated at {payload["generated_at"]}</div>
      <div class="summary-grid">
        <div class="stat"><div class="label">Skills</div><div class="value" id="summary-skills">0</div></div>
        <div class="stat"><div class="label">Usage Events</div><div class="value" id="summary-usage">0</div></div>
        <div class="stat"><div class="label">Findings</div><div class="value" id="summary-findings">0</div></div>
        <div class="stat"><div class="label">Usage Status</div><div class="value" id="summary-usage-status">-</div></div>
      </div>
      <div class="stats-grid">
        <div class="stat"><div class="label">Resolved HERMES_HOME</div><div class="muted" id="resolved-home"></div></div>
        <div class="stat"><div class="label">Hermes Base Home</div><div class="muted" id="resolved-base-home"></div></div>
        <div class="stat"><div class="label">Scan Scope</div><div class="muted" id="scan-scope"></div></div>
        <div class="stat"><div class="label">Effective Roots</div><div class="muted" id="effective-roots"></div></div>
      </div>
      <div id="mismatch-notice"></div>
    </div>

    <div class="nav">
      <button class="tab active" data-view="overview">Overview</button>
      <button class="tab" data-view="skills">Skills</button>
      <button class="tab" data-view="findings">Findings</button>
    </div>

    <section class="view active" id="view-overview">
      <div class="panel">
        <h2>Overview</h2>
        <div id="overview-content"></div>
      </div>
    </section>

    <section class="view" id="view-skills">
      <div class="panel">
        <h2>Skills</h2>
        <div class="filters">
          <input id="search" type="search" placeholder="Search name, description, trigger terms">
          <select id="filter-category"><option value="">All categories</option></select>
          <select id="filter-source"><option value="">All sources</option></select>
          <select id="filter-root"><option value="">All roots</option></select>
          <select id="filter-profile"><option value="">All installed profiles</option></select>
          <select id="filter-finding">
            <option value="">All statuses</option>
            <option value="has_findings">Has findings</option>
            <option value="no_findings">No findings</option>
          </select>
        </div>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Description</th>
              <th>Category</th>
              <th>Profiles</th>
              <th>Sources / Roots</th>
              <th>Paths</th>
              <th>Modified</th>
            </tr>
          </thead>
          <tbody id="skills-body"></tbody>
        </table>
      </div>
    </section>

    <section class="view" id="view-findings">
      <div class="panel">
        <h2>Findings</h2>
        <div id="findings-content"></div>
      </div>
    </section>
  </div>
  <script>
    const data = {dashboard_data};

    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[char]));
    }}

    function setText(id, value) {{
      document.getElementById(id).textContent = value ?? "";
    }}

    function populateSummary() {{
      setText("summary-skills", data.inventory_summary.skills);
      setText("summary-usage", data.doctor_summary.usage_events ?? 0);
      setText("summary-findings", data.doctor_summary.findings ?? 0);
      setText("summary-usage-status", data.doctor_summary.usage_logging_status ?? (data.report_available ? "unknown" : "not-run"));
      setText("resolved-home", data.resolved_hermes_home || "-");
      setText("resolved-base-home", data.resolved_hermes_base_home || "-");
      setText("scan-scope", data.scan_scope);
      setText("effective-roots", (data.effective_roots || []).join("\\n"));
      if (data.mismatch_notice) {{
        document.getElementById("mismatch-notice").innerHTML = `<div class="warning">${{escapeHtml(data.mismatch_notice)}}</div>`;
      }}
    }}

    function renderOverview() {{
      const categoryRows = Object.entries(data.inventory_summary.categories || {{}})
        .map(([key, value]) => `<div class="chip">${{escapeHtml(key)}}: ${{value}}</div>`)
        .join("");
      const sourceRows = Object.entries(data.inventory_summary.sources || {{}})
        .map(([key, value]) => `<div class="chip">${{escapeHtml(key)}}: ${{value}}</div>`)
        .join("");
      const rootRows = Object.entries(data.inventory_summary.roots || {{}})
        .map(([key, value]) => `<div class="chip">${{escapeHtml(key)}}: ${{value}}</div>`)
        .join("");
      const installedProfileRows = Object.entries(data.inventory_summary.installed_profiles || {{}})
        .map(([key, value]) => `<div class="chip">${{escapeHtml(key)}}: ${{value}}</div>`)
        .join("");
      const loadedProfileRows = Object.entries(data.inventory_summary.loaded_profiles || {{}})
        .map(([key, value]) => `<div class="chip">${{escapeHtml(key)}}: ${{value}}</div>`)
        .join("");
      document.getElementById("overview-content").innerHTML = `
        <div class="kv"><div class="k">Doctor report</div><div>${{data.report_available ? "Loaded" : "Not found"}}</div></div>
        <div class="kv"><div class="k">Categories</div><div class="chips">${{categoryRows || '<span class="muted">No skills</span>'}}</div></div>
        <div class="kv"><div class="k">Installed profiles</div><div class="chips">${{installedProfileRows || '<span class="muted">No profile metadata</span>'}}</div></div>
        <div class="kv"><div class="k">Loaded profiles</div><div class="chips">${{loadedProfileRows || '<span class="muted">No profile-aware usage events</span>'}}</div></div>
        <div class="kv"><div class="k">Sources</div><div class="chips">${{sourceRows || '<span class="muted">No sources</span>'}}</div></div>
        <div class="kv"><div class="k">Roots</div><div class="chips">${{rootRows || '<span class="muted">No roots</span>'}}</div></div>
      `;
    }}

    function populateFilters() {{
      const mappings = [
        ["filter-category", [...new Set(data.skills.map((item) => item.category))].sort()],
        ["filter-source", [...new Set(data.skills.flatMap((item) => item.sources || []))].sort()],
        ["filter-root", [...new Set(data.skills.flatMap((item) => item.roots || []))].sort()],
        ["filter-profile", [...new Set(data.skills.flatMap((item) => item.installed_profiles || []))].sort()],
      ];
      for (const [id, values] of mappings) {{
        const select = document.getElementById(id);
        for (const value of values) {{
          const option = document.createElement("option");
          option.value = value;
          option.textContent = value;
          select.appendChild(option);
        }}
      }}
    }}

    function filteredSkills() {{
      const search = document.getElementById("search").value.trim().toLowerCase();
      const category = document.getElementById("filter-category").value;
      const source = document.getElementById("filter-source").value;
      const root = document.getElementById("filter-root").value;
      const profile = document.getElementById("filter-profile").value;
      const finding = document.getElementById("filter-finding").value;
      return data.skills.filter((skill) => {{
        const haystack = [
          skill.name,
          skill.description,
          ...(skill.paths || []),
          ...(skill.roots || []),
          ...(skill.installed_profiles || []),
          ...(skill.loaded_profiles || []),
          ...(skill.trigger_terms || []),
        ].join(" ").toLowerCase();
        if (search && !haystack.includes(search)) return false;
        if (category && skill.category !== category) return false;
        if (source && !(skill.sources || []).includes(source)) return false;
        if (root && !(skill.roots || []).includes(root)) return false;
        if (profile && !(skill.installed_profiles || []).includes(profile)) return false;
        if (finding === "has_findings" && !(skill.findings || []).length) return false;
        if (finding === "no_findings" && (skill.findings || []).length) return false;
        return true;
      }});
    }}

    function renderSkills() {{
      const rows = filteredSkills().map((skill) => {{
        const findingChips = (skill.findings || []).map((finding) => {{
          const level = finding.severity === "high" ? "danger" : "warn";
          return `<span class="chip ${{level}}">${{escapeHtml(finding.kind)}}</span>`;
        }}).join("");
        const installedProfileChips = (skill.installed_profiles || []).map((profile) => `<span class="chip">${{escapeHtml(profile)}}</span>`).join("");
        const loadedProfileChips = (skill.loaded_profiles || []).map((profile) => `<span class="chip warn">${{escapeHtml(profile)}}</span>`).join("");
        const sourceChips = (skill.sources || []).map((source) => `<span class="chip">${{escapeHtml(source)}}</span>`).join("");
        const rootLines = (skill.roots || []).map((root) => `<div class="muted">${{escapeHtml(root)}}</div>`).join("");
        const pathLinks = (skill.paths || []).map((path) => `<a class="file-link" href="file://${{encodeURI(path)}}" target="_blank">${{escapeHtml(path)}}</a>`).join("<br>");
        return `<tr>
          <td>
            <div><strong>${{escapeHtml(skill.name)}}</strong></div>
            <div class="chips">${{findingChips}}</div>
          </td>
          <td>
            <div>${{escapeHtml(skill.description || "(no description)")}}</div>
            <div class="muted" title="${{escapeHtml(skill.category_reason)}}">category rule: ${{escapeHtml(skill.category_reason)}}</div>
          </td>
          <td>
            <span class="chip">${{escapeHtml(skill.category)}}</span>
            <div class="muted">copies: ${{escapeHtml(skill.copy_count)}}</div>
          </td>
          <td>
            <div class="chips">${{installedProfileChips || '<span class="muted">none</span>'}}</div>
            <div class="muted" style="margin-top:6px;">loaded:</div>
            <div class="chips">${{loadedProfileChips || '<span class="muted">none</span>'}}</div>
          </td>
          <td>
            <div class="chips">${{sourceChips}}</div>
            <div style="margin-top:6px;">${{rootLines}}</div>
          </td>
          <td>
            ${{pathLinks}}
          </td>
          <td>${{escapeHtml(skill.modified_at)}}</td>
        </tr>`;
      }});
      document.getElementById("skills-body").innerHTML = rows.join("") || `<tr><td colspan="6" class="empty">No skills match the current filters.</td></tr>`;
    }}

    function findingTitle(finding) {{
      if (finding.kind === "duplicate_candidate" && finding.evidence && finding.evidence.other_skill) {{
        return `${{finding.kind}}: ${{finding.skill_name}} ↔ ${{finding.evidence.other_skill}}`;
      }}
      return `${{finding.kind}}: ${{finding.skill_name}}`;
    }}

    function renderFindings() {{
      const findings = data.findings || [];
      if (!findings.length) {{
        document.getElementById("findings-content").innerHTML = `<div class="empty">${{data.report_available ? "No active findings." : "Doctor report not found. Run doctor first, then reopen this dashboard."}}</div>`;
        return;
      }}
      document.getElementById("findings-content").innerHTML = findings.map((finding) => `
        <div class="finding-card">
          <h3>${{escapeHtml(findingTitle(finding))}}</h3>
          <div class="finding-meta">
            <span class="chip">${{escapeHtml(finding.kind)}}</span>
            <span class="chip ${{finding.severity === "high" ? "danger" : "warn"}}">${{escapeHtml(finding.severity)}}</span>
            <span class="chip">${{escapeHtml(finding.feedback_status || "none")}}</span>
          </div>
          <div class="kv"><div class="k">Finding ID</div><div>${{escapeHtml(finding.finding_id || "")}}</div></div>
          <div class="kv"><div class="k">Message</div><div>${{escapeHtml(finding.message || "")}}</div></div>
          <div class="kv"><div class="k">Recommendation</div><div>${{escapeHtml(finding.recommendation || "")}}</div></div>
          <div class="kv"><div class="k">Evidence</div><div><pre>${{escapeHtml(JSON.stringify(finding.evidence || {{}}, null, 2))}}</pre></div></div>
        </div>
      `).join("");
    }}

    function bindTabs() {{
      for (const tab of document.querySelectorAll(".tab")) {{
        tab.addEventListener("click", () => {{
          for (const candidate of document.querySelectorAll(".tab")) candidate.classList.remove("active");
          for (const view of document.querySelectorAll(".view")) view.classList.remove("active");
          tab.classList.add("active");
          document.getElementById(`view-${{tab.dataset.view}}`).classList.add("active");
        }});
      }}
    }}

    function bindFilters() {{
      for (const id of ["search", "filter-category", "filter-source", "filter-root", "filter-profile", "filter-finding"]) {{
        document.getElementById(id).addEventListener("input", renderSkills);
        document.getElementById(id).addEventListener("change", renderSkills);
      }}
    }}

    populateSummary();
    renderOverview();
    populateFilters();
    renderSkills();
    renderFindings();
    bindTabs();
    bindFilters();
  </script>
</body>
</html>
"""


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
    if args.root:
        roots = [Path(root).expanduser() for root in args.root]
        scan_context = {
            "resolved_hermes_home": str(resolve_hermes_home()) if args.host == "hermes" else None,
            "effective_roots": [str(root) for root in roots],
            "scan_scope": "explicit_root",
        }
    else:
        roots, scan_context = discover_roots(args.host, args.scan_scope)
    statuses = adapter_statuses(roots, args.host, bool(args.root))
    skills = scan_skills(roots, args.host)
    write_index_with_context(args.state_dir, skills, statuses, scan_context)
    print(
        json.dumps(
            {
                "indexed": len(skills),
                "state_dir": str(args.state_dir),
                "adapter_status": [asdict(status) for status in statuses],
                "resolved_hermes_home": scan_context.get("resolved_hermes_home"),
                "effective_roots": scan_context.get("effective_roots", []),
                "scan_scope": scan_context.get("scan_scope"),
            },
            ensure_ascii=False,
        )
    )
    return 0


def command_import(args: argparse.Namespace) -> int:
    event_files = [Path(path).expanduser() for path in args.events] if args.events else discover_event_files(args.agent)
    status = import_events(event_files, args.state_dir, args.agent)
    write_usage_status(args.state_dir, status)
    print(
        json.dumps(
            {
                "imported": status.imported,
                "state_dir": str(args.state_dir),
                "usage_available": status.usage_available,
                "usage_logging_status": status.usage_logging_status,
                "diagnosis_code": status.diagnosis_code,
                "diagnosis": status.diagnosis,
                "resolved_hermes_home": status.resolved_hermes_home,
                "usage_log_path": status.usage_log_path,
                "health_log_path": status.health_log_path,
                "files_missing": status.files_missing,
            },
            ensure_ascii=False,
        )
    )
    return 0


def command_report(args: argparse.Namespace) -> int:
    skills = read_index(args.state_dir)
    events = read_events(args.state_dir)
    usage_status = read_usage_status(args.state_dir)
    raw_findings = build_findings(skills, events, args.stale_days, usage_status)
    findings, suppressed_findings, feedback_applied = apply_feedback(raw_findings, read_feedback(args.state_dir))
    payload = report_payload(
        skills,
        events,
        findings,
        usage_status,
        read_adapter_status(args.state_dir),
        read_scan_context(args.state_dir),
        suppressed_findings,
        feedback_applied,
    )
    if args.format == "md":
        sys.stdout.write(render_markdown(payload, args.language))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    if args.root:
        roots = [Path(root).expanduser() for root in args.root]
        scan_context = {
            "resolved_hermes_home": str(resolve_hermes_home()) if args.host == "hermes" else None,
            "effective_roots": [str(root) for root in roots],
            "scan_scope": "explicit_root",
        }
    else:
        roots, scan_context = discover_roots(args.host, args.scan_scope)
    statuses = adapter_statuses(roots, args.host, bool(args.root))
    skills = scan_skills(roots, args.host)
    write_index_with_context(args.state_dir, skills, statuses, scan_context)
    event_files = [Path(path).expanduser() for path in args.events] if args.events else discover_event_files(args.agent)
    usage_status = import_events(event_files, args.state_dir, args.agent)
    write_usage_status(args.state_dir, usage_status)
    events = read_events(args.state_dir)
    raw_findings = build_findings(skills, events, args.stale_days, usage_status)
    findings, suppressed_findings, feedback_applied = apply_feedback(raw_findings, read_feedback(args.state_dir))
    payload = report_payload(
        skills,
        events,
        findings,
        usage_status,
        [asdict(status) for status in statuses],
        scan_context,
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


def command_dashboard(args: argparse.Namespace) -> int:
    if args.root:
        roots = [Path(root).expanduser() for root in args.root]
        scan_context = {
            "resolved_hermes_home": str(resolve_hermes_home()) if args.host == "hermes" else None,
            "resolved_hermes_base_home": str(resolve_hermes_base_home()) if args.host == "hermes" else None,
            "effective_roots": [str(root) for root in roots],
            "scan_scope": "explicit_root",
        }
    else:
        roots, scan_context = discover_dashboard_roots(args.host, args.scan_scope)
    skills = scan_skills(roots, args.host)
    report_json_path = Path(args.report_json).expanduser() if args.report_json else Path(args.state_dir) / "skill-health-report.json"
    report_payload_data = read_report_payload(report_json_path)
    rows = dashboard_skills(skills, report_payload_data, scan_context, read_events(args.state_dir))
    payload = dashboard_payload(skills, rows, scan_context, report_payload_data)
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_dashboard_html(payload), encoding="utf-8")
    print(json.dumps({"dashboard_path": str(output_path), "skills": len(rows), "report_available": report_payload_data is not None}, ensure_ascii=False))
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
    scan.add_argument("--scan-scope", choices=["local_only", "local_plus_external"], default=DEFAULT_SCAN_SCOPE)
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
    doctor.add_argument("--scan-scope", choices=["local_only", "local_plus_external"], default=DEFAULT_SCAN_SCOPE)
    doctor.add_argument("--events", action="append", default=[], help="JSONL event file to import. May be repeated.")
    doctor.add_argument("--stale-days", type=int, default=90)
    doctor.add_argument("--language", choices=["en", "zh"], default="en")
    doctor.add_argument("--output-dir", default=str(DEFAULT_STATE_DIR))
    doctor.set_defaults(func=command_doctor)

    dashboard = subparsers.add_parser("dashboard", help="Generate a local HTML dashboard for Hermes skill inventory and doctor findings.")
    dashboard.add_argument("--root", action="append", default=[], help="Skill root to scan. May be repeated.")
    dashboard.add_argument("--host", choices=["custom", "openclaw", "hermes"], default="hermes")
    dashboard.add_argument("--scan-scope", choices=["local_only", "local_plus_external"], default=DEFAULT_SCAN_SCOPE)
    dashboard.add_argument("--report-json", default="", help="Existing doctor JSON report to visualize. Defaults to <state-dir>/skill-health-report.json.")
    dashboard.add_argument("--output", default=str(DEFAULT_STATE_DIR / "skill-health-dashboard.html"))
    dashboard.set_defaults(func=command_dashboard)

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
