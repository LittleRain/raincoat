# Review and edit schema

`edits.json` connects the HTML page to the renderer:

```json
{"source":"/absolute/path/match.mp4","plan":"standard","output":{"resolution":"original","video_bitrate_kbps":null},"clips":[{"id":"rally-003","keep":true,"start":312.4,"end":338.8}],"weights":{"rally_length":0.25,"estimated_shot_count":0.20,"movement_intensity":0.20,"attack_defense_switch":0.15,"net_play":0.10,"audio_energy":0.10},"confirmed":false}
```

The renderer must refuse to run when `confirmed` is false unless the user explicitly requests a non-interactive default render. Revalidate timestamps and reject unexpected overlaps before concatenation.
