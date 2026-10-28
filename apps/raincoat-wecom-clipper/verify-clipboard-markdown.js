#!/usr/bin/env node
"use strict";

const markdown = require("./clipboard_markdown.js");

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}\nExpected:\n${expected}\n\nActual:\n${actual}`);
  }
}

function textNode(text) {
  return {
    nodeType: 3,
    textContent: text,
  };
}

function element(tagName, attrs = {}, children = []) {
  const node = {
    nodeType: 1,
    tagName: String(tagName || "").toUpperCase(),
    childNodes: children,
    hidden: Boolean(attrs.hidden),
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
    },
    querySelectorAll(selector) {
      const matches = [];
      const wanted = String(selector || "").toUpperCase();
      walk(this, (candidate) => {
        if (candidate.nodeType === 1 && candidate.tagName === wanted) {
          matches.push(candidate);
        }
      });
      return matches;
    },
  };

  node.children = children.filter((child) => child && child.nodeType === 1);
  return node;
}

function walk(node, visit) {
  visit(node);
  if (!node.childNodes) return;
  node.childNodes.forEach((child) => walk(child, visit));
}

function run() {
  const root = element("div", {}, [
    element("h2", {}, [textNode("Weekly Report")]),
    element("p", {}, [
      textNode("Overview "),
      element("strong", {}, [textNode("important")]),
      textNode(" "),
      element("a", { href: "https://example.com" }, [textNode("link")]),
    ]),
    element("ul", {}, [
      element("li", {}, [textNode("First")]),
      element("li", {}, [textNode("Second")]),
    ]),
    element("table", {}, [
      element("tr", {}, [
        element("th", {}, [textNode("Name")]),
        element("th", {}, [textNode("Value")]),
      ]),
      element("tr", {}, [
        element("td", {}, [textNode("CTR")]),
        element("td", {}, [
          element("ul", {}, [
            element("li", {}, [textNode("12%")]),
            element("li", {}, [textNode("13%")]),
          ]),
        ]),
      ]),
    ]),
    element("p", {}, [textNode("1772516797616@eJ Microsoft YaHei 000000")]),
  ]);

  const actualFragment = markdown.fragmentToMarkdown(root);
  const expectedFragment = [
    "## Weekly Report",
    "",
    "Overview **important** [link](https://example.com)",
    "",
    "- First",
    "- Second",
    "",
    "| Name | Value |",
    "| --- | --- |",
    "| CTR | - 12%<br>- 13% |",
  ].join("\n");

  assertEqual(actualFragment, expectedFragment, "fragmentToMarkdown should keep structure and remove noise");

  const plain = markdown.plainTextToMarkdown("Line 1\r\n1772516797616@eJ\r\nMicrosoft YaHei\r\nLine 2");
  assertEqual(plain, "Line 1\n\nLine 2", "plainTextToMarkdown should strip noise tokens");

  console.log("OK: clipboard markdown conversion");
}

run();
