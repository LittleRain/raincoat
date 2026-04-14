---
name: wxurl2md
description: Use when converting WeCom doc URLs into local markdown for AI analysis, especially when direct URL fetch returns shell HTML, tables lose numeric columns, or browser login-state capture is required.
---

# wxurl2md

Convert WeCom docs to local markdown with login-state browser capture, then produce AI-ready outputs.

## Inputs

- One WeCom doc URL: `https://doc.weixin.qq.com/doc/w3_xxx?scode=xxx`
- Or a URL file (one URL per line, `#` comments allowed)
- Optional output dir (default `/tmp`)
- Optional capture wait time in ms (default `12000`)

## Run

Use the bundled script:

```bash
bash /Users/raincai/Documents/GitHub/raincoat/skills/wxurl2md/scripts/run-wecom-doc.sh \
  --url "https://doc.weixin.qq.com/doc/w3_xxx?scode=xxx" \
  --out-dir /tmp
```

Batch mode:

```bash
bash /Users/raincai/Documents/GitHub/raincoat/skills/wxurl2md/scripts/run-wecom-doc.sh \
  --url-file /path/to/wecom_urls.txt \
  --out-dir /tmp
```

If needed, run the capture script directly:

```bash
node /Users/raincai/Documents/GitHub/raincoat/tools/wecom_capture_opendoc.js \
  --url "https://doc.weixin.qq.com/doc/w3_xxx?scode=xxx" \
  --out-dir /tmp \
  --wait-ms 12000
```

## Workflow

1. Open the target URL in local Chrome with login state.
2. Capture network + runtime payload (`opendoc`, keyframe when available).
3. Generate outputs and use `*_for_ai.md` as primary AI input.
4. If content seems missing, verify against `*_keyframe.json` and `*_full_fidelity_clean.md` before concluding capture failure.

## Outputs

- `*_for_ai.md`: primary file for AI ingestion (least lossy)
- `*_ai_accuracy.md`: cleaner but may drop noisy lines
- `*_full_fidelity.md`: raw mutation text for debugging
- `*_full_fidelity_clean.md`: control-char-cleaned raw text
- `*_keyframe.json`: strongest evidence source for completeness checks
- `*_network_hits.json`: request trace for troubleshooting
- `wxurl2md_batch_report_*.txt`: batch execution summary (`OK/FAIL` + output paths)

## Guardrails

- Do not rely on direct URL HTML fetch as the source of truth.
- Do not use `*_ai_accuracy.md` as the only verification artifact.
- Preserve numeric metric cells in table-like blocks (counts, percentages).

## Troubleshooting Reference

For common failure modes and fixes, read:
[runbook.md](/Users/raincai/Documents/GitHub/raincoat/skills/wxurl2md/references/runbook.md)
