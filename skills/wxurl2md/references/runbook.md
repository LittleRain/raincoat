# wxurl2md Runbook

## Common Failures

### 1) Only shell HTML captured

Symptom:
- output contains page shell text but not正文

Fix:
- ensure local Chrome is logged in
- increase `--wait-ms` to 30000~45000
- verify `*_network_hits.json` contains `dop-api/opendoc`

### 2) Content appears missing

Symptom:
- `*_ai_accuracy.md` misses sections

Check order:
1. `*_for_ai.md`
2. `*_full_fidelity_clean.md`
3. `*_keyframe.json`

If present in keyframe/raw but absent in `ai_accuracy`, it is a cleaning policy issue.

### 3) Table first column only, numeric columns missing

Symptom:
- labels exist, counts/percentages missing

Fix:
- preserve pure numeric metric cells in capture filtering
- rerun capture and compare the specific block in `*_for_ai.md`

### 4) Tail has noisy style tokens

Symptom:
- lines like `z4m2zt*5`, `*U`, `N@:`, `Table Grid*`

Fix:
- keep source artifacts unchanged
- apply stricter style-noise filtering in `wecom_archive.py`

## Verification Checklist

- project/title keywords present
- key metrics present (`xx%`, counts)
- package/config lines preserved when relevant (`SNAPSHOT`, `groupId`, `artifactId`, `version`)
- no accidental loss of business conclusions

## Batch Mode

URL file format (one URL per line):

```text
# WeCom docs
https://doc.weixin.qq.com/doc/w3_xxx?scode=xxx
https://doc.weixin.qq.com/doc/w3_yyy?scode=yyy
```

Run:

```bash
bash /Users/raincai/Documents/GitHub/raincoat/skills/wxurl2md/scripts/run-wecom-doc.sh \
  --url-file /path/to/wecom_urls.txt \
  --out-dir /tmp
```

Result:

- `wxurl2md_batch_report_*.txt` in output dir
- Each URL has `OK/FAIL` and corresponding output file paths
