#!/usr/bin/env node
"use strict";

const writer = require("./vault_writer.js");
const markdown = require("./clipboard_markdown.js");

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}\nExpected: ${expected}\nActual: ${actual}`);
  }
}

function chooseClipboardMarkdown(payload) {
  const plainText = String(payload.text || "");
  const html = String(payload.html || "");
  const normalizedText = markdown.plainTextToMarkdown(plainText);
  const normalizedHtml = html ? markdown.htmlToMarkdown(html) : "";

  if (normalizedHtml && !looksLikeMarkdown(normalizedText)) {
    return { source: "clipboard-html", markdown: normalizedHtml };
  }
  if (normalizedText) {
    return { source: "clipboard-text", markdown: normalizedText };
  }
  if (normalizedHtml) {
    return { source: "clipboard-html", markdown: normalizedHtml };
  }
  return { source: "clipboard-empty", markdown: "" };
}

function looksLikeMarkdown(text) {
  const value = String(text || "");
  return (
    /^#{1,6}\s/m.test(value) ||
    /^\s*[-*]\s/m.test(value) ||
    /^\s*\d+\.\s/m.test(value) ||
    /^\|.+\|$/m.test(value) ||
    /\[[^\]]+\]\([^)]+\)/.test(value)
  );
}

function run() {
  assertEqual(
    writer.normalizeRelativeFolder("  Clippings / WeCom / Weekly  "),
    "Clippings/WeCom/Weekly",
    "normalizeRelativeFolder should sanitize path parts"
  );

  assertEqual(
    writer.sanitizeFileName('Weekly: "Test" / Draft'),
    "Weekly Test Draft",
    "sanitizeFileName should strip forbidden characters"
  );

  assertEqual(
    writer.renderFileName("{{title}} {{timestamp}}", {
      title: "Weekly Report",
      timestamp: "2026-04-27 09.30.00",
      date: "2026-04-27",
    }),
    "Weekly Report 2026-04-27 09.30.00",
    "renderFileName should render title and timestamp placeholders"
  );

  const choice1 = chooseClipboardMarkdown({
    text: "Just copied plain text",
    html: "<h2>Weekly</h2><p>Body</p>",
  });
  assertEqual(choice1.source, "clipboard-html", "HTML should win when plain text is not Markdown");

  const choice2 = chooseClipboardMarkdown({
    text: "# Weekly\n\n- One",
    html: "<h2>Weekly</h2><ul><li>One</li></ul>",
  });
  assertEqual(choice2.source, "clipboard-text", "Existing Markdown plain text should be preserved");

  console.log("OK: vault writer helpers");
}

run();
