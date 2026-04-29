#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const parser = require("./richtext_parser.js");

const samplePath =
  process.argv[2] ||
  "/tmp/wecom_obsidian_test/wecom_w3_Af0A3AZAAEcCNEDEHQuJoT90Y7b9g_opendoc.json";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function findLineIndex(lines, fragment) {
  return lines.findIndex((line) => line.includes(fragment));
}

function findLineIndexAfter(lines, fragment, minIndex) {
  for (let i = Math.max(0, minIndex + 1); i < lines.length; i += 1) {
    if (lines[i].includes(fragment)) return i;
  }
  return -1;
}

function main() {
  const jsonPath = path.resolve(samplePath);
  const raw = fs.readFileSync(jsonPath, "utf8");
  const parsed = JSON.parse(raw);

  const lines = parser.extractRichTextLinesFromParsed(parsed);
  const joined = lines.join("\n");

  assert(lines.length > 50, `line count too small: ${lines.length}`);

  const anchor1 = "为什么会带来圈子内的发布";
  const anchor2 = "O1：市集在承接自营商品的前提下，提升商品丰富度以及合规性，提升买家数到4k";
  const actionAnchor = "本周动作";
  const o3Anchor = "O3：提升魔力赏二手市集内的交易链路";
  const w1Anchor = "4月W1（0327-0402）";

  const i1 = findLineIndex(lines, anchor1);
  const i2 = findLineIndexAfter(lines, anchor2, i1);
  const iAction = findLineIndex(lines, actionAnchor);
  const iO3 = findLineIndex(lines, o3Anchor);
  const iW1 = findLineIndex(lines, w1Anchor);

  assert(i1 >= 0, `missing anchor: ${anchor1}`);
  assert(i2 >= 0, `anchor order invalid: '${anchor2}' should appear after '${anchor1}'`);
  assert(iAction >= 0, `missing anchor: ${actionAnchor}`);
  assert(iO3 >= 0, `missing anchor: ${o3Anchor}`);
  assert(iW1 >= 0, `missing anchor: ${w1Anchor}`);

  const noisePatterns = [
    /\d{10,}@eJ/,
    /Microsoft YaHei/,
    /\b000000\b/,
    /^[\[\]{}|~\\/:;,.+\-_*@=]{1,8}$/m,
  ];

  for (const pattern of noisePatterns) {
    assert(!pattern.test(joined), `noise leaked: ${pattern}`);
  }

  console.log(`OK: ${path.basename(jsonPath)}`);
  console.log(`lines=${lines.length} anchor1=${i1} anchor2=${i2} action=${iAction} o3=${iO3} w1=${iW1}`);
}

main();
