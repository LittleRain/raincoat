chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.action !== "openObsidianUrl" || !message.url) {
    return false;
  }

  chrome.tabs.create({ url: message.url, active: true }, () => {
    sendResponse({ ok: !chrome.runtime.lastError, error: chrome.runtime.lastError?.message || "" });
  });

  return true;
});
