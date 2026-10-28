#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const parser = require("./richtext_parser.js");

const samplePath =
  process.argv[2] ||
  path.join(__dirname, "tests/fixtures/synthetic-opendoc.json");

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

  assert(lines.length >= 10, `missing synthetic content: ${lines.length}`);

  const anchor1 = "为什么需要调整导出顺序";
  const anchor2 = "O1：合成目标，订单达到4000单";
  const actionAnchor = "本周动作";
  const o3Anchor = "O2：合成目标，转化率提升至12.5%";
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

  for (const fragment of ["12345", "678.90", "负责人小雨", "截止下周三", "先测试，再发布"]) {
    assert(joined.includes(fragment), `lost fact: ${fragment}`);
  }
  assert(iO3 > i2, "objective order changed");

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
