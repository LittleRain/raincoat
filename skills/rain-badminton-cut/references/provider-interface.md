# Analyzer provider interface

Providers consume a video path, local feature summary, candidate ranges, and sampled evidence. They return validated JSON:

```json
{"provider":"minimax-cli","candidates":[{"start":312.4,"end":338.8,"completeness_confidence":0.91,"signals":{"rally_length":0.86,"estimated_shot_count":0.78,"movement_intensity":0.83,"attack_defense_switch":0.72,"net_play":0.35,"audio_energy":0.61},"reasons":["连续多拍","快速攻防转换","结尾检测到死球"]}]}
```

Validate timestamps against duration, reject NaN/infinite values, and preserve the local candidate when provider boundaries are invalid. Provider prose is explanatory; selection uses validated signals and configured weights.

For `minimax-cli`, use a temporary evidence directory containing sampled JPEG frames. The verified command shape is `mmx vision describe --image <path> --prompt <question>` (or `--file-id` for an uploaded file). Never assume the CLI can ingest a full match video. Keep this adapter separate so a custom command can replace it.
