(function (globalScope) {
  "use strict";

  const LINE_BREAK_CODES = new Set([10, 13]);
  const PARAGRAPH_BREAK_CODES = new Set([11, 12, 29, 30, 31]);

  function decodeRichTextBlob(blob) {
    const text = String(blob || "").trim();
    if (text.length < 64 || !/^[A-Za-z0-9+/=]+$/.test(text)) return "";
    try {
      if (typeof atob === "function" && typeof TextDecoder !== "undefined") {
        const binary = atob(text);
        const bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0));
        return new TextDecoder("utf-8", { fatal: false }).decode(bytes);
      }

      if (typeof Buffer !== "undefined") {
        return Buffer.from(text, "base64").toString("utf8");
      }
    } catch (_) {
      return "";
    }
    return "";
  }

  function classifyToken(raw, boundary) {
    if (boundary) return "break";
    const text = String(raw || "").trim();
    if (!text) return "unknown";
    if (isOperationLogToken(text)) return "oplog";
    if (isStyleToken(text)) return "style";
    if (isProtocolToken(text)) return "protocol";
    if (isContentFragment(text)) return "content";
    return "unknown";
  }

  function tokenizeRichText(decoded) {
    const tokens = [];
    let buffer = "";

    const flushBuffer = () => {
      const raw = buffer.trim();
      buffer = "";
      if (!raw) return;
      tokens.push({ raw, kind: classifyToken(raw, null) });
    };

    for (const ch of String(decoded || "")) {
      const code = ch.charCodeAt(0);

      if (LINE_BREAK_CODES.has(code)) {
        flushBuffer();
        tokens.push({ raw: ch, kind: "break", boundary: "line" });
        continue;
      }

      if (PARAGRAPH_BREAK_CODES.has(code)) {
        flushBuffer();
        tokens.push({ raw: ch, kind: "break", boundary: "paragraph" });
        continue;
      }

      if ((code >= 0 && code <= 31) || code === 127) {
        flushBuffer();
        tokens.push({ raw: ch, kind: "break", boundary: "line" });
        continue;
      }

      buffer += ch;
    }

    flushBuffer();
    return tokens;
  }

  function normalizeContentToken(raw) {
    let text = String(raw || "");

    text = text
      .replace(/\bHYPERLINK\b/g, " ")
      .replace(/\bMENTION_WXWORK\b/g, " ")
      .replace(/\bhttps?:\/\/\S+/g, " ")
      .replace(/\bp\.\d{8,}\b/g, " ")
      .replace(/\b\d{10,}@eJ[\w\-+/=]*/g, " ")
      .replace(/\\t[a-z0-9]+/gi, " ")
      .replace(/[\u0000-\u001F\u007F]/g, " ")
      .replace(/\uFFFD+/g, " ")
      .replace(/\s+/g, " ")
      .trim();

    if (!text) return "";
    if (/normalLink|FromPaste|docLink|\btdf\b|\btdk\b|\btdfi\b/i.test(text)) return "";
    if (isOperationLogToken(text) || isStyleToken(text)) return "";
    if (/^[{}\[\]",]+$/.test(text)) return "";
    if (/^[!"/()*.:<=>@A-Za-z0-9-]{2,6}$/.test(text) && /[:@*]/.test(text)) return "";
    return text;
  }

  function shouldJoinWithPreviousFragment(previous, next) {
    if (!previous || !next) return false;
    if (/[（([{【“"'《]$/.test(previous)) return true;
    if (/^[，。！？；：、,.!?;:)\]】》」”'"]/u.test(next)) return true;
    if (/[\u4e00-\u9fff]$/.test(previous) && /^[\u4e00-\u9fff]/.test(next)) return true;
    return false;
  }

  function isContentFragment(text) {
    if (!text) return false;
    if (text.length < 2 || text.length > 1200) return false;
    if (/^[\uFFFD\u0000-\u001F\u007F\s]+$/.test(text)) return false;
    if (/normalLink|FromPaste|docLink|\btdf\b|\btdk\b|\btdfi\b/i.test(text)) return false;
    if (/[\u4e00-\u9fff]/.test(text)) return true;
    if (/[A-Za-z]/.test(text) && text.length > 3) return true;
    if (/^\d+(\.\d+)?%?$/.test(text)) return true;
    return false;
  }

  function isOperationLogToken(text) {
    return /^\d{10,}@eJ/.test(text) || /^p\.\d{8,}/.test(text);
  }

  function isStyleToken(text) {
    if (/^"[^"]{1,40}"[*:J]?$/.test(text)) return true;
    if (/^(000000|111111|222222|333333|444444|555555|666666|777777|888888|999999|k@)$/.test(text)) return true;
    if (/^(Microsoft YaHei|PingFang SC|Arial|Helvetica)$/.test(text)) return true;
    if (/^[!"/()*.:<=>@A-Za-z0-9-]{2,6}$/.test(text) && /[:@*]/.test(text)) return true;
    if (/^[\[\]{}|~\\/:;,.+\-_*@=]{1,8}$/.test(text)) return true;
    if (/^[\[\]{}|~\\/:;,.+\-_*@=][0-9]$/.test(text)) return true;
    return false;
  }

  function isProtocolToken(text) {
    return /\b(HYPERLINK|MENTION_WXWORK)\b/.test(text);
  }

  function rebuildLines(tokens) {
    const lines = [];
    let current = "";
    let pendingParagraphBreak = false;

    const flushCurrent = () => {
      const text = current.trim();
      current = "";
      if (!text) return;
      lines.push(text);
    };

    for (const token of tokens || []) {
      if (token.kind === "break") {
        flushCurrent();
        if (token.boundary === "paragraph") pendingParagraphBreak = true;
        continue;
      }

      if (token.kind === "oplog" || token.kind === "style") continue;
      if (token.kind !== "content" && token.kind !== "protocol" && token.kind !== "unknown") continue;

      const text = normalizeContentToken(token.raw);
      if (!text) continue;

      if (pendingParagraphBreak) {
        if (lines.length && lines[lines.length - 1] !== "") lines.push("");
        pendingParagraphBreak = false;
      }

      if (!current) {
        current = text;
        continue;
      }

      if (shouldJoinWithPreviousFragment(current, text)) {
        current += text;
        continue;
      }

      if (/[A-Za-z0-9]$/.test(current) && /^[A-Za-z0-9]/.test(text)) {
        current += ` ${text}`;
      } else {
        current += text;
      }
    }

    flushCurrent();
    return dedupeAdjacent(lines.filter((line) => keepString(line)));
  }

  function reorderNarrativeBlocks(lines) {
    const list = [...(lines || [])];
    if (!list.length) return list;

    const firstWhy = list.findIndex((line) => /^为什么/.test(line) || /为什么/.test(line));
    const objectiveIndices = list
      .map((line, index) => (/^O\d+[：:]/.test(line) ? index : -1))
      .filter((index) => index >= 0);

    if (firstWhy < 0 || !objectiveIndices.length || objectiveIndices.some((index) => index > firstWhy)) {
      return list;
    }

    const blockStart = objectiveIndices[0];
    let blockEnd = blockStart + 1;
    while (blockEnd < list.length) {
      const text = list[blockEnd];
      if (blockEnd > blockStart + 4 && /^(?:\d{1,2}月W\d|本周动作|上周todo|核心数据|##?\s|【)/.test(text)) {
        break;
      }
      blockEnd += 1;
    }

    const block = list.slice(blockStart, blockEnd);
    const remaining = list.slice(0, blockStart).concat(list.slice(blockEnd));
    const insertAfter = remaining.findIndex((line) => /^为什么/.test(line) || /为什么/.test(line));
    if (insertAfter < 0) return list;

    const before = remaining.slice(0, insertAfter + 1);
    const after = remaining.slice(insertAfter + 1);
    return dedupeAdjacent(before.concat(block, after));
  }

  function extractRichTextLinesFromParsed(parsed) {
    const out = [];
    const blobs = parsed?.clientVars?.collab_client_vars?.initialAttributedText?.text;
    if (Array.isArray(blobs)) {
      for (const blob of blobs) {
        const decoded = decodeRichTextBlob(blob);
        if (!decoded) continue;
        const tokens = tokenizeRichText(decoded);
        for (const line of rebuildLines(tokens)) out.push(line);
      }
    }
    return reorderNarrativeBlocks(dedupeAdjacent(out).filter((line) => keepString(line)));
  }

  function keepString(value) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    if (text.length < 2 || text.length > 800) return false;
    if (/^https?:\/\//.test(text)) return false;
    if (/^[{}\[\]",]+$/.test(text)) return false;
    if (/^[\uFFFD\u0000-\u001F\u007F\s]+$/.test(text)) return false;
    if ((text.match(/\uFFFD/g) || []).length >= 2) return false;
    if (isOperationLogToken(text)) return false;
    if (isStyleToken(text)) return false;
    if (/normalLink|FromPaste|docLink|\btdf\b|\btdk\b|\btdfi\b/i.test(text)) return false;
    return true;
  }

  function dedupeAdjacent(items) {
    const out = [];
    for (const item of items || []) {
      if (!out.length || out[out.length - 1] !== item) out.push(item);
    }
    return out;
  }

  const api = {
    decodeRichTextBlob,
    tokenizeRichText,
    classifyToken,
    normalizeContentToken,
    rebuildLines,
    extractRichTextLinesFromParsed,
    shouldJoinWithPreviousFragment,
    isOperationLogToken,
    isStyleToken,
    isProtocolToken,
    isContentFragment,
    keepString,
    dedupeAdjacent,
    reorderNarrativeBlocks,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }

  globalScope.WecomRichTextParser = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
