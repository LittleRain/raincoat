const DEFAULT_SETTINGS = {
  copyAdapterEnabled: true,
  preserveHtml: true,
  relativeFolder: "Clippings/WeCom",
  filenameTemplate: "{{title}} {{timestamp}}",
  directoryName: "",
};

const markdownApi = globalThis.WecomClipboardMarkdown;
const vaultWriter = globalThis.WecomVaultWriter;

const state = {
  tab: null,
  page: null,
  directoryHandle: null,
};

const els = {
  pageStatus: document.getElementById("pageStatus"),
  sourceUrlValue: document.getElementById("sourceUrlValue"),
  directoryStatus: document.getElementById("directoryStatus"),
  pickDirectory: document.getElementById("pickDirectory"),
  relativeFolder: document.getElementById("relativeFolder"),
  filenameTemplate: document.getElementById("filenameTemplate"),
  enabled: document.getElementById("enabled"),
  preserveHtml: document.getElementById("preserveHtml"),
  syncButton: document.getElementById("syncButton"),
  result: document.getElementById("result"),
};

init().catch((error) => {
  setResult(error.message || String(error), true);
});

els.pickDirectory.addEventListener("click", () => {
  chooseDirectory().catch((error) => setResult(error.message || String(error), true));
});
els.syncButton.addEventListener("click", () => {
  syncClipboard().catch((error) => {
    setBusy(false);
    setResult(error.message || String(error), true);
  });
});
els.enabled.addEventListener("change", persistSettings);
els.preserveHtml.addEventListener("change", persistSettings);
els.relativeFolder.addEventListener("change", persistSettings);
els.filenameTemplate.addEventListener("change", persistSettings);

async function init() {
  const settings = await chrome.storage.sync.get(DEFAULT_SETTINGS);
  els.enabled.checked = settings.copyAdapterEnabled !== false;
  els.preserveHtml.checked = settings.preserveHtml !== false;
  els.relativeFolder.value = settings.relativeFolder || DEFAULT_SETTINGS.relativeFolder;
  els.filenameTemplate.value = settings.filenameTemplate || DEFAULT_SETTINGS.filenameTemplate;

  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  state.tab = tabs[0] || null;
  state.page = parseSupportedUrl(state.tab?.url || "");
  els.sourceUrlValue.textContent = state.tab?.url || "-";
  els.pageStatus.textContent = state.page
    ? `当前页面：${state.page.host}`
    : "当前页面不是企微/腾讯文档。";

  state.directoryHandle = await vaultWriter.loadDirectoryHandle();
  await refreshDirectoryStatus(settings.directoryName || "");
  setResult("", false, false);
}

async function chooseDirectory() {
  if (typeof showDirectoryPicker !== "function") {
    throw new Error("当前 Chrome 不支持在插件弹窗中选择文件夹。");
  }

  const handle = await showDirectoryPicker({ mode: "readwrite" });
  const granted = await vaultWriter.ensureDirectoryPermission(handle, true);
  if (!granted) throw new Error("没有获得文件夹写入权限。");

  state.directoryHandle = handle;
  await vaultWriter.saveDirectoryHandle(handle);
  await chrome.storage.sync.set({ directoryName: handle.name || "" });
  await refreshDirectoryStatus(handle.name || "");
  setResult("保存目录已连接。", false, true);
}

async function syncClipboard() {
  setBusy(true);
  const settings = await persistSettings();

  if (!state.directoryHandle) {
    throw new Error("请先选择保存文件夹。");
  }

  const hasPermission = await vaultWriter.ensureDirectoryPermission(state.directoryHandle, false);
  if (!hasPermission) {
    const granted = await vaultWriter.ensureDirectoryPermission(state.directoryHandle, true);
    if (!granted) {
      await vaultWriter.clearDirectoryHandle();
      state.directoryHandle = null;
      await chrome.storage.sync.set({ directoryName: "" });
      await refreshDirectoryStatus("");
      throw new Error("文件夹权限已失效，请重新选择。");
    }
  }

  const clipboard = await readClipboard();
  const rawText = String(clipboard.text || "").trim();
  if (!rawText || rawText.length <= 50) {
    setBusy(false);
    alert("请先复制文档的文本内容");
    setResult("", false, false);
    return;
  }

  const selected = chooseClipboardMarkdown(clipboard);
  if (!selected.markdown.trim()) {
    throw new Error("剪贴板里没有可用文本，请先复制文档内容。");
  }

  const title = cleanTitle(state.tab?.title || "WeCom Document");
  const timestamp = formatTimestamp(new Date());
  const date = timestamp.slice(0, 10);
  const fileName = vaultWriter.renderFileName(settings.filenameTemplate, { title, timestamp, date });
  const markdown = buildMarkdown({
    title,
    url: state.tab?.url || "",
    source: selected.source,
    text: selected.markdown,
  });

  const savedName = await vaultWriter.writeMarkdownFile(
    state.directoryHandle,
    settings.relativeFolder,
    fileName,
    markdown
  );

  setBusy(false);
  setResult(`已保存：${savedName}`, false, true);
  await promptOpenObsidian(savedName, settings);
}

async function promptOpenObsidian(savedName, settings) {
  const vaultName = state.directoryHandle?.name || "";
  const relativeFile = [settings.relativeFolder, savedName].filter(Boolean).join("/");
  const fileUrl = buildObsidianFileUrl(vaultName, relativeFile);
  const response = await chrome.runtime.sendMessage({
    action: "openObsidianUrl",
    url: fileUrl,
  });

  if (!response?.ok) {
    const fallback = await chrome.runtime.sendMessage({
      action: "openObsidianUrl",
      url: "obsidian://open",
    });
    if (!fallback?.ok) {
      alert(`打开 Obsidian 失败：${fallback?.error || response?.error || "unknown error"}`);
    }
  }
}

function buildObsidianFileUrl(vaultName, relativeFile) {
  const cleanVault = String(vaultName || "").trim();
  const cleanFile = String(relativeFile || "").replace(/^\/+/, "");
  if (!cleanVault || !cleanFile) return "obsidian://open";
  return `obsidian://open?vault=${encodeURIComponent(cleanVault)}&file=${encodeURIComponent(cleanFile)}`;
}

async function persistSettings() {
  const settings = {
    copyAdapterEnabled: els.enabled.checked,
    preserveHtml: els.preserveHtml.checked,
    relativeFolder: vaultWriter.normalizeRelativeFolder(els.relativeFolder.value),
    filenameTemplate: els.filenameTemplate.value.trim() || DEFAULT_SETTINGS.filenameTemplate,
  };
  els.relativeFolder.value = settings.relativeFolder;
  els.filenameTemplate.value = settings.filenameTemplate;
  await chrome.storage.sync.set(settings);
  await refreshDirectoryStatus((await chrome.storage.sync.get("directoryName")).directoryName || "");
  return settings;
}

async function refreshDirectoryStatus(storedName) {
  if (!state.directoryHandle) {
    els.directoryStatus.textContent = "尚未选择文件夹";
    els.pickDirectory.textContent = "选择文件夹";
    return;
  }

  const permission = await vaultWriter.ensureDirectoryPermission(state.directoryHandle, false);
  const label = state.directoryHandle.name || storedName || "已选文件夹";
  const relativeFolder = vaultWriter.normalizeRelativeFolder(els.relativeFolder.value || DEFAULT_SETTINGS.relativeFolder);
  const fullPath = [label, relativeFolder].filter(Boolean).join("/");
  els.directoryStatus.textContent = permission
    ? `将会保存到以下文件夹：${fullPath}`
    : `文件夹需要重新授权：${fullPath}`;
  els.pickDirectory.textContent = "修改文件夹";
}

async function readClipboard() {
  const payload = { text: "", html: "" };

  if (navigator.clipboard && typeof navigator.clipboard.read === "function") {
    try {
      const items = await navigator.clipboard.read();
      for (const item of items) {
        if (!payload.html && item.types.includes("text/html")) {
          payload.html = await (await item.getType("text/html")).text();
        }
        if (!payload.text && item.types.includes("text/plain")) {
          payload.text = await (await item.getType("text/plain")).text();
        }
      }
    } catch (_) {
      // Fallback to readText below.
    }
  }

  if (!payload.text && navigator.clipboard && typeof navigator.clipboard.readText === "function") {
    payload.text = await navigator.clipboard.readText();
  }

  return payload;
}

function chooseClipboardMarkdown(payload) {
  const plainText = String(payload.text || "");
  const html = String(payload.html || "");
  const normalizedText = markdownApi.plainTextToMarkdown(plainText);
  const normalizedHtml = html ? markdownApi.htmlToMarkdown(html) : "";

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

function buildMarkdown({ title, url, source, text }) {
  const lineCount = text ? text.split("\n").filter(Boolean).length : 0;
  return [
    "---",
    `source_url: ${JSON.stringify(url)}`,
    `source: ${JSON.stringify(url)}`,
    `captured: ${JSON.stringify(new Date().toISOString())}`,
    `clipper: ${JSON.stringify("wecom-vault-sync")}`,
    `extractor: ${JSON.stringify(source)}`,
    `line_count: ${JSON.stringify(lineCount)}`,
    "---",
    "",
    `# ${title || "WeCom Document"}`,
    "",
    text.trim(),
    "",
  ].join("\n");
}

function parseSupportedUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    if (
      url.hostname === "doc.weixin.qq.com" ||
      url.hostname === "docs.qq.com" ||
      url.hostname.endsWith(".docs.qq.com")
    ) {
      return { host: url.hostname };
    }
  } catch (_) {
    return null;
  }
  return null;
}

function cleanTitle(value) {
  return String(value || "WeCom Document")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\.(docx?|md)$/i, "");
}

function formatTimestamp(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  const second = String(date.getSeconds()).padStart(2, "0");
  return `${year}-${month}-${day} ${hour}.${minute}.${second}`;
}

function setBusy(isBusy) {
  els.pickDirectory.disabled = isBusy;
  els.syncButton.disabled = isBusy;
}

function setResult(message, isError, isOk) {
  els.result.textContent = message || "";
  els.result.className = isError ? "error" : isOk ? "ok" : "";
}
