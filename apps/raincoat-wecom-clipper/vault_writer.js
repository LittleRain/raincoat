(function (globalScope) {
  "use strict";

  const DB_NAME = "wecom-copy-adapter";
  const STORE_NAME = "handles";
  const HANDLE_KEY = "vault-root";

  async function openDb() {
    return await new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => {
        request.result.createObjectStore(STORE_NAME);
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error("Failed to open IndexedDB."));
    });
  }

  async function saveDirectoryHandle(handle) {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).put(handle, HANDLE_KEY);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error || new Error("Failed to save directory handle."));
    });
  }

  async function loadDirectoryHandle() {
    const db = await openDb();
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const request = tx.objectStore(STORE_NAME).get(HANDLE_KEY);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error || new Error("Failed to load directory handle."));
    });
  }

  async function clearDirectoryHandle() {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).delete(HANDLE_KEY);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error || new Error("Failed to clear directory handle."));
    });
  }

  async function ensureDirectoryPermission(handle, shouldRequest) {
    if (!handle) return false;
    const options = { mode: "readwrite" };
    if (typeof handle.queryPermission === "function") {
      const permission = await handle.queryPermission(options);
      if (permission === "granted") return true;
    }
    if (shouldRequest && typeof handle.requestPermission === "function") {
      const permission = await handle.requestPermission(options);
      return permission === "granted";
    }
    return false;
  }

  async function ensureSubdirectory(rootHandle, relativeFolder) {
    let currentHandle = rootHandle;
    for (const part of normalizeRelativeFolder(relativeFolder).split("/").filter(Boolean)) {
      currentHandle = await currentHandle.getDirectoryHandle(part, { create: true });
    }
    return currentHandle;
  }

  async function writeMarkdownFile(rootHandle, relativeFolder, filename, content) {
    const targetDir = await ensureSubdirectory(rootHandle, relativeFolder);
    const finalName = await createUniqueName(targetDir, ensureMarkdownExtension(sanitizeFileName(filename)));
    const fileHandle = await targetDir.getFileHandle(finalName, { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(content);
    await writable.close();
    return finalName;
  }

  async function createUniqueName(dirHandle, filename) {
    const extIndex = filename.lastIndexOf(".");
    const stem = extIndex > 0 ? filename.slice(0, extIndex) : filename;
    const ext = extIndex > 0 ? filename.slice(extIndex) : "";

    let candidate = `${stem}${ext}`;
    let counter = 1;
    while (await fileExists(dirHandle, candidate)) {
      candidate = `${stem}-${String(counter).padStart(2, "0")}${ext}`;
      counter += 1;
    }
    return candidate;
  }

  async function fileExists(dirHandle, filename) {
    try {
      await dirHandle.getFileHandle(filename);
      return true;
    } catch (_) {
      return false;
    }
  }

  function ensureMarkdownExtension(filename) {
    return /\.md$/i.test(filename) ? filename : `${filename}.md`;
  }

  function normalizeRelativeFolder(value) {
    return String(value || "")
      .split("/")
      .map((part) => sanitizePathSegment(part))
      .filter(Boolean)
      .join("/");
  }

  function sanitizePathSegment(value) {
    return String(value || "")
      .replace(/[\\:*?"<>|]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 80);
  }

  function sanitizeFileName(value) {
    const sanitized = String(value || "")
      .replace(/[\\/:*?"<>|#^[\]]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 120);
    return sanitized || "Untitled";
  }

  function renderFileName(template, context) {
    return String(template || "{{title}} {{timestamp}}")
      .replace(/\{\{\s*title\s*\}\}/g, context.title || "Untitled")
      .replace(/\{\{\s*timestamp\s*\}\}/g, context.timestamp || "")
      .replace(/\{\{\s*date\s*\}\}/g, context.date || "")
      .replace(/\s+/g, " ")
      .trim();
  }

  const api = {
    saveDirectoryHandle,
    loadDirectoryHandle,
    clearDirectoryHandle,
    ensureDirectoryPermission,
    writeMarkdownFile,
    normalizeRelativeFolder,
    sanitizeFileName,
    renderFileName,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }

  globalScope.WecomVaultWriter = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
