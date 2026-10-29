#!/usr/bin/env python3
"""Build expected-output-inventory.json from a normalized report spec.

The parser intentionally accepts both the structured spec template and common
Chinese requirement-table prose. It is conservative: explicit counts win; table
rows with chart/table words are used as a fallback for legacy requirements.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SECTION_RE = re.compile(r"^###\s+(?P<title>.+?)\s*$")
SECTION_ID_RE = re.compile(r"section_id\s*[:：]\s*`?(?P<id>[A-Za-z0-9_-]+)`?")
CHART_COUNT_RE = re.compile(r"(?:charts_count|expected charts count|图表数量)\s*[:：]\s*(?P<count>\d+)", re.I)
TABLE_COUNT_RE = re.compile(r"(?:tables_count|expected tables count|表格数量)\s*[:：]\s*(?P<count>\d+)", re.I)
METRICS_RE = re.compile(r"(?:required_metrics|required metrics|必需指标|核心指标)\s*[:：]\s*(?P<metrics>.+)", re.I)


def _section_id(index: int, title: str) -> str:
    explicit = SECTION_ID_RE.search(title)
    if explicit:
        return explicit.group("id")
    return f"s{index}"


def _metric_entries(raw: str) -> list[dict[str, str]]:
    raw = raw.strip().strip("`")
    if not raw or raw in {"[]", "-"}:
        return []
    parts = re.split(r"[,，、/|]+", raw)
    return [{"metric_name": part.strip().strip("`")} for part in parts if part.strip().strip("`")]


def _classify_requirement_row(line: str) -> str | None:
    if not line.startswith("|"):
        return None
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if len(cells) < 2:
        return None
    first = cells[0]
    if not first or set(first) <= {"-", " "} or first in {"图表类型", "类型"}:
        return None
    if first.startswith("表") or first.startswith("数据表"):
        return "table"
    if "图" in first:
        return "chart"
    return None


def _extract_sections(markdown: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_data_source = False
    collecting_metrics = False

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("## 数据源") or line.startswith("## data_contract"):
            in_data_source = True
        match = SECTION_RE.match(line)
        if match and not in_data_source:
            title = match.group("title").strip()
            current = {
                "section_id": _section_id(len(sections) + 1, title),
                "title": title,
                "charts": 0,
                "tables": 0,
                "required_metrics": [],
            }
            sections.append(current)
            collecting_metrics = False
            continue

        if current is None or in_data_source:
            continue

        section_id_match = SECTION_ID_RE.search(line)
        if section_id_match:
            current["section_id"] = section_id_match.group("id")

        chart_count_match = CHART_COUNT_RE.search(line)
        if chart_count_match:
            current["charts"] = int(chart_count_match.group("count"))

        table_count_match = TABLE_COUNT_RE.search(line)
        if table_count_match:
            current["tables"] = int(table_count_match.group("count"))

        metrics_match = METRICS_RE.search(line)
        if metrics_match:
            current["required_metrics"].extend(_metric_entries(metrics_match.group("metrics")))
            collecting_metrics = True
            continue

        if re.search(r"(?:required_metrics|required metrics|必需指标|核心指标)\s*[:：]\s*$", line, re.I):
            collecting_metrics = True
            continue

        if line.startswith("-") and ":" in line:
            collecting_metrics = False

        if collecting_metrics and line.startswith("-") and ":" not in line:
            metric = line.lstrip("-").strip().strip("`")
            if metric:
                current["required_metrics"].append({"metric_name": metric})
            continue

        row_type = _classify_requirement_row(line)
        if row_type == "chart" and chart_count_match is None:
            current["charts"] += 1
        elif row_type == "table" and table_count_match is None:
            current["tables"] += 1

    return sections


def build_inventory(spec_path: Path) -> dict[str, Any]:
    markdown = spec_path.read_text(encoding="utf-8")
    sections = _extract_sections(markdown)
    required_metrics: list[dict[str, str]] = []
    seen_metrics: set[str] = set()

    for section in sections:
        unique_section_metrics = []
        for metric in section["required_metrics"]:
            name = metric["metric_name"]
            if name not in {item["metric_name"] for item in unique_section_metrics}:
                unique_section_metrics.append(metric)
            if name not in seen_metrics:
                required_metrics.append(metric)
                seen_metrics.add(name)
        section["required_metrics"] = unique_section_metrics

    return {
        "source_requirement": str(spec_path),
        "description": "Expected rendered view counts generated from the normalized report spec.",
        "totals": {
            "sections": len(sections),
            "charts": sum(int(section["charts"]) for section in sections),
            "tables": sum(int(section["tables"]) for section in sections),
        },
        "required_metrics": required_metrics,
        "judgment_metrics": [],
        "sections": [
            {
                "section_id": section["section_id"],
                "title": section["title"],
                "charts": int(section["charts"]),
                "tables": int(section["tables"]),
                "required_metrics": section["required_metrics"],
            }
            for section in sections
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build expected report output inventory from a normalized spec.")
    parser.add_argument("--spec", required=True, help="Path to normalized spec markdown")
    parser.add_argument("--output", required=True, help="Path to write expected-output-inventory.json")
    args = parser.parse_args()

    inventory = build_inventory(Path(args.spec))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
