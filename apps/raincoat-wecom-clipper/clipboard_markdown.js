(function (globalScope) {
  "use strict";

  const NOISE_PATTERNS = [
    /\d{10,}@eJ[\w+/=-]*/g,
    /\bp\.\d{8,}\b/g,
    /\b(?:Microsoft YaHei|PingFang SC|Arial|Helvetica)\b/g,
    /\b(?:000000|111111|222222|333333|444444|555555|666666|777777|888888|999999)\b/g,
    /\b(?:HYPERLINK|MENTION_WXWORK|normalLink|docLink|FromPaste|inline)\b/g,
    /\btd(?:f|k|fi|fu|lt|lf|tf|sub)\b/gi,
  ];

  function plainTextToMarkdown(text) {
    return cleanupMarkdown(
      String(text || "")
        .replace(/\r\n?/g, "\n")
        .split("\n")
        .map((line) => normalizeInlineText(line))
        .join("\n")
    );
  }

  function htmlToMarkdown(html) {
    if (typeof DOMParser === "undefined") {
      return plainTextToMarkdown(html);
    }

    const parser = new DOMParser();
    const doc = parser.parseFromString(`<div data-root="true">${html || ""}</div>`, "text/html");
    const root = doc.body.firstElementChild;
    return fragmentToMarkdown(root);
  }

  function fragmentToMarkdown(root) {
    if (!root) return "";
    const state = { references: [] };
    const markdown = renderChildBlocks(root, state).join("\n\n");
    return cleanupMarkdown(markdown);
  }

  function selectionToMarkdown(root, fallbackText) {
    const markdown = fragmentToMarkdown(root);
    if (markdown.trim()) return markdown;
    return plainTextToMarkdown(fallbackText);
  }

  function renderChildBlocks(parent, state) {
    const out = [];
    const children = Array.from(parent.childNodes || []);
    for (const child of children) {
      const block = renderBlockNode(child, state, 0);
      if (!block) continue;
      out.push(block);
    }
    return out;
  }

  function renderBlockNode(node, state, depth) {
    if (!node) return "";
    if (node.nodeType === 3) {
      return normalizeInlineText(node.textContent || "");
    }
    if (node.nodeType !== 1) return "";

    const tag = node.tagName.toLowerCase();
    if (shouldIgnoreNode(node, tag)) return "";

    if (tag === "table") return renderTable(node, state);
    if (tag === "ul") return renderList(node, state, depth, false);
    if (tag === "ol") return renderList(node, state, depth, true);
    if (tag === "pre") return renderPre(node);

    const headingLevel = tag.match(/^h([1-6])$/);
    if (headingLevel) {
      const text = normalizeInlineText(renderInlineChildren(node, state));
      return text ? `${"#".repeat(Number(headingLevel[1]))} ${text}` : "";
    }

    if (tag === "blockquote") {
      const text = renderChildBlocks(node, state).join("\n");
      if (!text.trim()) return "";
      return text
        .split("\n")
        .map((line) => (line ? `> ${line}` : ">"))
        .join("\n");
    }

    if (tag === "hr") return "---";

    if (isBlockTag(tag)) {
      const text = renderMixedBlock(node, state, depth);
      return text;
    }

    return normalizeInlineText(renderInlineNode(node, state));
  }

  function renderMixedBlock(node, state, depth) {
    const childBlocks = [];
    let inlineBuffer = "";

    const flushInline = () => {
      const text = normalizeInlineText(inlineBuffer);
      inlineBuffer = "";
      if (text) childBlocks.push(text);
    };

    for (const child of Array.from(node.childNodes || [])) {
      if (child.nodeType === 1 && isBlockTag(child.tagName.toLowerCase())) {
        flushInline();
        const rendered = renderBlockNode(child, state, depth + 1);
        if (rendered) childBlocks.push(rendered);
      } else {
        inlineBuffer += renderInlineNode(child, state);
      }
    }

    flushInline();
    return childBlocks.join("\n\n");
  }

  function renderInlineChildren(node, state) {
    let out = "";
    for (const child of Array.from(node.childNodes || [])) {
      out += renderInlineNode(child, state);
    }
    return out;
  }

  function renderInlineNode(node, state) {
    if (!node) return "";
    if (node.nodeType === 3) return sanitizeTextFragment(node.textContent || "");
    if (node.nodeType !== 1) return "";

    const tag = node.tagName.toLowerCase();
    if (shouldIgnoreNode(node, tag)) return "";

    if (tag === "br") return "\n";
    if (tag === "code") return wrapCode(renderInlineChildren(node, state));
    if (tag === "strong" || tag === "b") return wrapDelimited(renderInlineChildren(node, state), "**");
    if (tag === "em" || tag === "i") return wrapDelimited(renderInlineChildren(node, state), "*");
    if (tag === "s" || tag === "del") return wrapDelimited(renderInlineChildren(node, state), "~~");
    if (tag === "a") return renderLink(node, state);
    if (tag === "img") return renderImage(node);

    return renderInlineChildren(node, state);
  }

  function renderList(listNode, state, depth, ordered) {
    const items = Array.from(listNode.children || []).filter((child) => child.tagName && child.tagName.toLowerCase() === "li");
    const out = [];

    items.forEach((item, index) => {
      const marker = ordered ? `${index + 1}. ` : "- ";
      const indent = "  ".repeat(depth);
      const lines = renderListItem(item, state, depth + 1).split("\n");
      if (!lines[0]) return;
      out.push(`${indent}${marker}${lines[0]}`);
      for (let i = 1; i < lines.length; i += 1) {
        out.push(`${indent}  ${lines[i]}`);
      }
    });

    return out.join("\n");
  }

  function renderListItem(node, state, depth) {
    const childBlocks = [];
    let inlineBuffer = "";

    const flushInline = () => {
      const text = normalizeInlineText(inlineBuffer);
      inlineBuffer = "";
      if (text) childBlocks.push(text);
    };

    for (const child of Array.from(node.childNodes || [])) {
      if (child.nodeType === 1) {
        const tag = child.tagName.toLowerCase();
        if (tag === "ul" || tag === "ol") {
          flushInline();
          const nested = renderList(child, state, depth, tag === "ol");
          if (nested) childBlocks.push(nested);
          continue;
        }
        if (isBlockTag(tag) && tag !== "span" && tag !== "a" && tag !== "strong" && tag !== "em" && tag !== "code") {
          flushInline();
          const rendered = renderBlockNode(child, state, depth);
          if (rendered) childBlocks.push(rendered);
          continue;
        }
      }
      inlineBuffer += renderInlineNode(child, state);
    }

    flushInline();
    return childBlocks.join("\n");
  }

  function renderTable(tableNode, state) {
    const rows = Array.from(tableNode.querySelectorAll("tr"))
      .map((row) =>
        Array.from(row.children || [])
          .filter((cell) => /^(td|th)$/i.test(cell.tagName))
          .map((cell) => escapeTableCell(renderTableCell(cell, state)))
      )
      .filter((row) => row.length);

    if (!rows.length) return "";

    const headerRow = rows[0];
    const bodyRows = rows.length > 1 ? rows.slice(1) : [];
    const normalizedRows = [headerRow].concat(
      bodyRows.map((row) => padRow(row, headerRow.length))
    );

    const lines = [
      `| ${padRow(headerRow, headerRow.length).join(" | ")} |`,
      `| ${new Array(headerRow.length).fill("---").join(" | ")} |`,
    ];

    normalizedRows.slice(1).forEach((row) => {
      lines.push(`| ${row.join(" | ")} |`);
    });

    return lines.join("\n");
  }

  function renderTableCell(cellNode, state) {
    const parts = [];
    let inlineBuffer = "";

    const flushInline = () => {
      const text = normalizeInlineText(inlineBuffer);
      inlineBuffer = "";
      if (text) parts.push(text);
    };

    for (const child of Array.from(cellNode.childNodes || [])) {
      if (child.nodeType === 1) {
        const tag = child.tagName.toLowerCase();
        if (tag === "ul" || tag === "ol") {
          flushInline();
          const list = renderList(child, state, 0, tag === "ol").replace(/\n/g, "<br>");
          if (list) parts.push(list);
          continue;
        }
        if (tag === "p" || tag === "div") {
          flushInline();
          const block = renderMixedBlock(child, state, 0).replace(/\n/g, "<br>");
          if (block) parts.push(block);
          continue;
        }
      }
      inlineBuffer += renderInlineNode(child, state);
    }

    flushInline();
    return parts.join("<br>");
  }

  function renderPre(node) {
    const text = (node.textContent || "").replace(/\r\n?/g, "\n").trimEnd();
    if (!text) return "";
    return `\`\`\`\n${text}\n\`\`\``;
  }

  function renderLink(node, state) {
    const label = normalizeInlineText(renderInlineChildren(node, state));
    const href = String(node.getAttribute("href") || "").trim();
    if (!label && !href) return "";
    if (!href) return label;
    return `[${escapeBracketText(label || href)}](${href})`;
  }

  function renderImage(node) {
    const alt = normalizeInlineText(node.getAttribute("alt") || "");
    const src = String(node.getAttribute("src") || "").trim();
    if (src) return `![${escapeBracketText(alt)}](${src})`;
    return alt;
  }

  function shouldIgnoreNode(node, tag) {
    if (["script", "style", "meta", "link", "noscript"].includes(tag)) return true;
    if (node.getAttribute && node.getAttribute("aria-hidden") === "true") return true;
    if (node.hidden) return true;
    const style = String(node.getAttribute?.("style") || "").toLowerCase();
    if (style.includes("display:none") || style.includes("visibility:hidden")) return true;
    return false;
  }

  function isBlockTag(tag) {
    return [
      "article", "aside", "blockquote", "div", "figcaption", "figure", "footer", "header",
      "li", "main", "nav", "ol", "p", "pre", "section", "table", "tbody", "thead", "tr", "ul",
      "h1", "h2", "h3", "h4", "h5", "h6"
    ].includes(tag);
  }

  function normalizeInlineText(text) {
    let normalized = sanitizeTextFragment(text)
      .replace(/[ ]*\n[ ]*/g, "\n")
      .trim();

    return normalized;
  }

  function sanitizeTextFragment(text) {
    let normalized = String(text || "")
      .replace(/\u00a0/g, " ")
      .replace(/\r\n?/g, "\n");

    NOISE_PATTERNS.forEach((pattern) => {
      normalized = normalized.replace(pattern, " ");
    });

    normalized = normalized
      .replace(/[ \t\f\v]+/g, " ")
      .replace(/^[\[\]{}|~\\/:;,.+\-_*@=]{1,8}$/gm, "");

    return normalized;
  }

  function cleanupMarkdown(markdown) {
    return String(markdown || "")
      .replace(/\r\n?/g, "\n")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .replace(/[ \t]{2,}/g, " ")
      .trim();
  }

  function wrapDelimited(text, delimiter) {
    const value = normalizeInlineText(text);
    return value ? `${delimiter}${value}${delimiter}` : "";
  }

  function wrapCode(text) {
    const value = normalizeInlineText(text);
    return value ? `\`${value.replace(/`/g, "\\`")}\`` : "";
  }

  function escapeBracketText(text) {
    return String(text || "").replace(/[[\]]/g, "\\$&");
  }

  function escapeTableCell(text) {
    return String(text || "").replace(/\|/g, "\\|");
  }

  function padRow(row, size) {
    const out = row.slice(0, size);
    while (out.length < size) out.push("");
    return out;
  }

  const api = {
    plainTextToMarkdown,
    htmlToMarkdown,
    fragmentToMarkdown,
    selectionToMarkdown,
    normalizeInlineText,
    sanitizeTextFragment,
    cleanupMarkdown,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }

  globalScope.WecomClipboardMarkdown = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
