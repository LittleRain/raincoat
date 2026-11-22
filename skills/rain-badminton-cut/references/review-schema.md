# Review and edit schema

`edits.json` connects the HTML page to the renderer:

```json
{"source":"/absolute/path/match.mp4","plan":"standard","mode":"person","target_description":"白衣黄裤","target_count":1,"output":{"resolution":"original","video_bitrate_kbps":null},"clips":[{"id":"rally-003","keep":true,"start":312.4,"end":338.8,"target_confirmed":true,"highlight":true,"note":"连续防守后得分"}],"weights":{"rally_length":0.25,"estimated_shot_count":0.20,"movement_intensity":0.20,"attack_defense_switch":0.15,"net_play":0.10,"audio_energy":0.10},"confirmed":false}
```

The renderer refuses unconfirmed edits, validates an optional `target_count` against the selected clips, and requires manually confirmed participation for `mode=person`. It revalidates timestamps and rejects unexpected overlaps before concatenation. Legacy edit files without the new fields remain renderable.

The review page also exports `badminton-chatcut-handoff.json` with the original absolute source path and confirmed ranges. `preview_source` is only for browser playback; it must not replace `source` in either exported JSON. See `docs/skills/chatcut-handoff.md` at the repository root.
