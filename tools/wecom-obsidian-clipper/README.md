# WeCom Vault Sync Chrome Extension

Chrome MV3 extension that adapts copied WeCom/Tencent document selections into stable Markdown and saves them as new files inside an authorized Obsidian vault directory.

## Install locally

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select this directory: `tools/wecom-obsidian-clipper`.

## Usage

1. Open a WeCom or Tencent document you already have permission to view.
2. Click the extension icon.
3. Click **Choose Vault Directory** and authorize your vault or a vault subdirectory once.
4. Optionally adjust the relative folder and filename template.
5. Select content in the document and press `Cmd+C` / `Ctrl+C`.
6. Click **Sync Clipboard**.

The extension still adapts clipboard `text/plain` into Markdown during the copy event. The popup then reads clipboard content, prefers HTML-derived Markdown when needed, and writes a new `.md` file into the authorized directory.

## Scope

- Handles authentication only indirectly: the current Chrome profile must already be logged in and authorized.
- Runs on `doc.weixin.qq.com` and `docs.qq.com` pages.
- Converts the user's current selection instead of exporting the whole document.
- Writes a new Markdown file for each sync.
- Preserves headings, paragraphs, lists, links, and basic tables.
- Images and complex embedded widgets are not preserved in this prototype.
