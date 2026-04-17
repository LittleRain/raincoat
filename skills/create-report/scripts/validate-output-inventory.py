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
        self._in_table = False
        self._current_table_section: str | None = None
        self._current_table_parts: list[str] = []
        self.table_text: list[str] = []
        self.section_table_text: dict[str, list[str]] = {}

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
            self._in_table = True
            self._current_table_section = self._current_section
            self._current_table_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._in_table:
            table_text = " ".join(part.strip() for part in self._current_table_parts if part.strip())
            self.table_text.append(table_text)
            if self._current_table_section:
                self.section_table_text.setdefault(self._current_table_section, []).append(table_text)
            self._in_table = False
            self._current_table_section = None
            self._current_table_parts = []
            return

        if tag == "section" and self._section_stack:
            self._current_section = self._section_stack.pop()

    def handle_data(self, data: str) -> None:
        self._text_parts.append(data)
        if self._current_section:
            self.section_text.setdefault(self._current_section, []).append(data)
        if self._in_table:
            self._current_table_parts.append(data)

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


def _string_entries(entries: Any, field_name: str) -> list[str]:
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise ValueError(f"{field_name} must be an array")
    values: list[str] = []
    for entry in entries:
        if not isinstance(entry, str):
            raise ValueError(f"each {field_name} entry must be a string")
        values.append(entry)
    return values


def _layout_entries(entries: Any) -> list[dict[str, Any]]:
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise ValueError("table_layout_contract must be an array")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each table_layout_contract entry must be an object")
    return entries


def _has_text(texts: list[str], expected: str) -> bool:
    return any(expected in text for text in texts)


def _validate_semantic_contract(contract: Any, parser: ReportHTMLParser, errors: list[str]) -> None:
    if contract is None:
        return
    if not isinstance(contract, dict):
        raise ValueError("semantic_contract must be an object")

    terms = contract.get("business_terms", [])
    if terms is None:
        terms = []
    if not isinstance(terms, list):
        raise ValueError("semantic_contract.business_terms must be an array")

    for term in terms:
        if not isinstance(term, dict):
            raise ValueError("each semantic business_term must be an object")
        name = term.get("name")
        if not name:
            raise ValueError("each semantic business_term needs name")
        needs_clarification = bool(term.get("needs_clarification"))
        if not needs_clarification and not (term.get("definition") or term.get("source_fields")):
            errors.append(f"semantic term {name} needs definition/source_fields or needs_clarification")
        if term.get("hard_constraint") and not needs_clarification and not term.get("source_fields"):
            errors.append(f"semantic term {name} source_fields expected for hard constraint")

    segment_rules = contract.get("segment_rules", [])
    if segment_rules is None:
        segment_rules = []
    if not isinstance(segment_rules, list):
        raise ValueError("semantic_contract.segment_rules must be an array")
    for rule in segment_rules:
        if not isinstance(rule, dict):
            raise ValueError("each semantic segment_rule must be an object")
        name = rule.get("segment_name")
        if not name:
            raise ValueError("each semantic segment_rule needs segment_name")
        if not rule.get("source_fields") and not (rule.get("rule_logic") or rule.get("allowed_categories")):
            errors.append(f"semantic segment rule {name} needs source_fields or rule_logic")

    examples = contract.get("semantic_examples", [])
    if examples is None:
        examples = []
    if not isinstance(examples, list):
        raise ValueError("semantic_contract.semantic_examples must be an array")
    for example in examples:
        if not isinstance(example, dict):
            raise ValueError("each semantic example must be an object")
        expected = example.get("expected", {})
        if not isinstance(expected, dict):
            raise ValueError("each semantic example expected must be an object")
        for field_name, expected_value in expected.items():
            value = str(expected_value)
            if value and value not in parser.text:
                errors.append(f"semantic example expected {field_name}={value}, found 0")


def _validate_layout_contract(layouts: Any, parser: ReportHTMLParser, errors: list[str]) -> None:
    for layout in _layout_entries(layouts):
        section_id = str(layout.get("section_id") or "")
        section_name = str(layout.get("section") or section_id or "global")
        section_text = parser.text_for_section(section_id) if section_id else parser.text
        table_texts = parser.section_table_text.get(section_id, []) if section_id else parser.table_text
        mode = layout.get("layout_mode")
        if not mode:
            raise ValueError("each table_layout_contract entry needs layout_mode")

        if layout.get("ambiguity_level") == "high":
            if not layout.get("source_phrase") or not layout.get("interpretation_reason"):
                errors.append(f"layout {section_name} high ambiguity needs source_phrase and interpretation_reason")

        if section_id and section_id not in parser.section_ids:
            errors.append(f"layout section {section_id} expected, found 0 matching sections")
            continue

        _validate_layout_mode(section_name, str(mode), layout, section_text, table_texts, errors)

        required_tables = layout.get("required_tables", [])
        if required_tables is None:
            required_tables = []
        if not isinstance(required_tables, list):
            raise ValueError("table_layout_contract.required_tables must be an array")
        if mode == "hybrid_section_with_subtables" and len(table_texts) < len(required_tables):
            errors.append(f"section {section_id or section_name} tables expected at least {len(required_tables)}, found {len(table_texts)}")
        for required_table in required_tables:
            if not isinstance(required_table, dict):
                raise ValueError("each required table layout entry must be an object")
            table_name = str(required_table.get("name") or "unnamed")
            if table_name != "unnamed" and table_name not in section_text:
                errors.append(f"section {section_id or section_name} table {table_name} expected, found 0")
            table_mode = str(required_table.get("layout_mode") or "dimension_as_rows")
            _validate_layout_mode(
                f"section {section_id or section_name} table {table_name}",
                table_mode,
                required_table,
                section_text,
                table_texts,
                errors,
            )


def _validate_layout_mode(
    label: str,
    mode: str,
    layout: dict[str, Any],
    section_text: str,
    table_texts: list[str],
    errors: list[str],
) -> None:
    if mode == "dimension_as_rows":
        for dimension in _string_entries(layout.get("row_dimensions", []), "row_dimensions"):
            if not _has_text(table_texts, dimension):
                errors.append(f"{label} dimension {dimension} expected in table, found 0")
        return

    if mode == "dimension_as_columns":
        for dimension in _string_entries(layout.get("column_dimensions", []), "column_dimensions"):
            if not _has_text(table_texts, dimension):
                errors.append(f"{label} column dimension {dimension} expected in table, found 0")
        return

    if mode == "separate_tables_by_dimension":
        instances = layout.get("required_table_instances", [])
        if instances is None:
            instances = []
        if not isinstance(instances, list):
            raise ValueError("required_table_instances must be an array")
        if len(table_texts) < len(instances):
            errors.append(f"{label} separate tables expected at least {len(instances)}, found {len(table_texts)}")
        for instance in instances:
            value = str(instance)
            if value and value not in section_text:
                errors.append(f"{label} table instance {value} expected, found 0")
        return

    if mode == "hybrid_section_with_subtables":
        return

    if mode == "unresolved":
        if not layout.get("source_phrase") or not layout.get("interpretation_reason"):
            errors.append(f"{label} unresolved layout needs source_phrase and interpretation_reason")
        return

    raise ValueError(f"unsupported layout_mode: {mode}")


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

    for dimension_name in _string_entries(inventory.get("required_dimensions", []), "required_dimensions"):
        if dimension_name not in parser.text:
            errors.append(f"dimension {dimension_name} expected, found 0")

    for required_text in _string_entries(inventory.get("required_text", []), "required_text"):
        if required_text not in parser.text:
            errors.append(f"required text {required_text} expected, found 0")

    _validate_semantic_contract(inventory.get("semantic_contract"), parser, errors)
    _validate_layout_contract(
        inventory.get("table_layout_contract", inventory.get("required_layouts", [])),
        parser,
        errors,
    )

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
        for dimension_name in _string_entries(section.get("required_dimensions", []), "section required_dimensions"):
            if dimension_name not in section_text:
                errors.append(f"section {section_id} dimension {dimension_name} expected, found 0")
        for required_text in _string_entries(section.get("required_text", []), "section required_text"):
            if required_text not in section_text:
                errors.append(f"section {section_id} required text {required_text} expected, found 0")

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
