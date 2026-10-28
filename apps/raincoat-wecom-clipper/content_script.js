(function () {
  "use strict";

  const markdownApi = globalThis.WecomClipboardMarkdown;
  const DEFAULT_SETTINGS = {
    copyAdapterEnabled: true,
    preserveHtml: true,
  };

  if (!markdownApi || !isSupportedPage(location.href)) {
    return;
  }

  let settings = { ...DEFAULT_SETTINGS };

  chrome.storage.sync.get(DEFAULT_SETTINGS, (stored) => {
    settings = { ...DEFAULT_SETTINGS, ...stored };
  });

  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== "sync") return;
    if (changes.copyAdapterEnabled) settings.copyAdapterEnabled = changes.copyAdapterEnabled.newValue;
    if (changes.preserveHtml) settings.preserveHtml = changes.preserveHtml.newValue;
  });

  document.addEventListener(
    "copy",
    (event) => {
      try {
        if (!settings.copyAdapterEnabled) return;
        if (!event.clipboardData) return;

        const selection = window.getSelection();
        if (!selection || selection.isCollapsed || !selection.rangeCount) return;

        const fragment = document.createElement("div");
        for (let i = 0; i < selection.rangeCount; i += 1) {
          const range = selection.getRangeAt(i);
          fragment.appendChild(range.cloneContents());
        }

        const plainText = selection.toString();
        const html = fragment.innerHTML;
        const markdown = markdownApi.selectionToMarkdown(fragment, plainText);
        if (!markdown || !markdown.trim()) return;

        event.preventDefault();
        event.clipboardData.setData("text/plain", markdown);

        if (settings.preserveHtml && html.trim()) {
          event.clipboardData.setData("text/html", html);
        }
      } catch (_) {
        // Preserve default browser copy behavior if conversion fails.
      }
    },
    true
  );

  function isSupportedPage(rawUrl) {
    try {
      const url = new URL(rawUrl);
      return (
        url.hostname === "doc.weixin.qq.com" ||
        url.hostname === "docs.qq.com" ||
        url.hostname.endsWith(".docs.qq.com")
      );
    } catch (_) {
      return false;
    }
  }
})();
