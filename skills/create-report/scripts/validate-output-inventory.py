#!/usr/bin/env python3
"""Validate rendered report HTML against expected output inventory.

The inventory is derived from the normalized spec, which itself is extracted from
需求.md. This validator intentionally checks required view and metric presence,
not visual correctness.
"""

from __future__ import annotations

import argparse
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


class ReportHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.section_ids: list[str] = []
        self.chart_count = 0
        self.table_count = 0
        self._section_stack: list[str | None] = []
        self._current_section: str | None = None
        self.section_counts: dict[str, dict[str, int]] = {}
        self._text_parts: list[str] = []
        self.section_text: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: v or "" for k, v in attrs}
        classes = set(attr.get("class", "").split())

        if tag == "section" and "section" in classes:
            section_id = attr.get("id", "")
            self.section_ids.append(section_id)
            self._section_stack.append(self._current_section)
            self._current_section = section_id
            if section_id:
                self.section_counts.setdefault(section_id, {"charts": 0, "tables": 0})
            return

        if "chart-container" in classes:
            self.chart_count += 1
            self._increment_section("charts")

        if tag == "table":
            self.table_count += 1
            self._increment_section("tables")

    def handle_endtag(self, tag: str) -> None:
        if tag == "section" and self._section_stack:
            self._current_section = self._section_stack.pop()

    def handle_data(self, data: str) -> None:
        self._text_parts.append(data)
        if self._current_section:
            self.section_text.setdefault(self._current_section, []).append(data)

    def _increment_section(self, key: str) -> None:
        if not self._current_section:
            return
        self.section_counts.setdefault(self._current_section, {"charts": 0, "tables": 0})
        self.section_counts[self._current_section][key] += 1

    @property
    def text(self) -> str:
        return " ".join(part.strip() for part in self._text_parts if part.strip())

    def text_for_section(self, section_id: str) -> str:
        return " ".join(part.strip() for part in self.section_text.get(section_id, []) if part.strip())


def _expected_int(container: dict[str, Any], key: str) -> int | None:
    value = container.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _metric_names(entries: Any, field_name: str) -> list[str]:
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise ValueError(f"{field_name} must be an array")

    names: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            names.append(entry)
            continue
        if not isinstance(entry, dict):
            raise ValueError(f"each {field_name} entry must be a string or object")
        name = entry.get("metric_name") or entry.get("name")
        if not name:
            raise ValueError(f"each {field_name} object needs metric_name")
        names.append(str(name))
    return names


def validate(inventory: dict[str, Any], html: str) -> list[str]:
    parser = ReportHTMLParser()
    parser.feed(html)

    errors: list[str] = []
    totals = inventory.get("totals", {})
    if not isinstance(totals, dict):
        raise ValueError("totals must be an object")

    actual_totals = {
        "sections": len(parser.section_ids),
        "charts": parser.chart_count,
        "tables": parser.table_count,
    }

    for key, actual in actual_totals.items():
        expected = _expected_int(totals, key)
        if expected is not None and expected != actual:
            errors.append(f"{key} expected {expected}, found {actual}")

    required_metrics = inventory.get("required_metrics", inventory.get("metrics", []))
    for metric_name in _metric_names(required_metrics, "required_metrics"):
        if metric_name not in parser.text:
            errors.append(f"metric {metric_name} expected, found 0")

    expected_sections = inventory.get("sections", [])
    if expected_sections is None:
        expected_sections = []
    if not isinstance(expected_sections, list):
        raise ValueError("sections must be an array")

    for section in expected_sections:
        if not isinstance(section, dict):
            raise ValueError("each section inventory entry must be an object")
        section_id = section.get("section_id")
        if not section_id:
            raise ValueError("each section inventory entry needs section_id")
        actual = parser.section_counts.get(str(section_id), {"charts": 0, "tables": 0})
        if section_id not in parser.section_counts:
            errors.append(f"section {section_id} expected, found 0 matching sections")
        for key in ("charts", "tables"):
            expected = _expected_int(section, key)
            if expected is not None and expected != actual[key]:
                errors.append(f"section {section_id} {key} expected {expected}, found {actual[key]}")
        section_text = parser.text_for_section(str(section_id))
        section_required_metrics = section.get("required_metrics", section.get("metrics", []))
        for metric_name in _metric_names(section_required_metrics, "section required_metrics"):
            if metric_name not in section_text:
                errors.append(f"section {section_id} metric {metric_name} expected, found 0")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate report chart/table/metric output against expected inventory.")
    parser.add_argument("--inventory", required=True, help="Path to expected-output-inventory.json")
    parser.add_argument("--html", required=True, help="Path to rendered report.html")
    args = parser.parse_args()

    inventory_path = Path(args.inventory)
    html_path = Path(args.html)
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    html = html_path.read_text(encoding="utf-8")

    errors = validate(inventory, html)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("output inventory validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
