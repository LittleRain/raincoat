---
name: rain-badminton-cut
description: Create conservative, reviewable badminton-video highlight candidates and a local montage. Use for horizontal badminton match cutting when a user can review boundaries before rendering; not for generating new videos.
---

# Rain Badminton Cut

Turn a badminton match video into a conservative, reviewable highlight montage. The primary invariant is rally completeness: include preparation/service, the rally, and the point-ending dead-ball or reset whenever inferable. If uncertain, keep extra context and mark low confidence.

## Workflow

1. Inspect the input with `ffprobe` and run `scripts/preflight.py`. Require local FFmpeg. For `minimax-cli`, verify `mmx --version`, `mmx auth status`, and `mmx quota`; never print credentials or store tokens in the project.
2. Load `config.yaml`, or use `config.example.yaml`. Keep analyzer, rally boundaries, scoring, and output settings independent.
3. Extract local one-second motion and audio-energy signals. Do not upload the original unless the configured provider explicitly supports it and the user requests that mode.
4. Use those signals to propose activity ranges with pre/post-roll safety margins. If signals are unreliable, generate conservative overlapping windows and flag the fallback.
5. If MiniMax refinement is explicitly requested, send only provider-requested sampled-image evidence. Prefer structured JSON. The model may refine boundaries and explain scores but must not override safety margins silently.
6. Score candidates with the local proxy signals and display their evidence. The MVP produces one editable review set;精选版、标准版、完整版 are a later enhancement.
7. Generate an HTML review page showing previews, timestamps, score, reasons, completeness confidence, and editable keep/remove bounds. For an end-to-end local MVP, use `scripts/run.py <video> --serve --open`; the review page's confirmation button creates `edits.json` and renders locally.
8. Render only after confirmation, using FFmpeg. Preserve source frame rate and resolution by default; for a size limit, show a resolution/bitrate tradeoff first.
9. Validate timestamps, playability, and truncation. Save `highlights.mp4`, `clips.json`, and `edits.json` in a separate output directory.

## Provider contract

Support `local-heuristic`, `minimax-cli`, and `custom-command`. Use `references/provider-interface.md` for the JSON contract. For MiniMax, invoke the installed CLI as a subprocess and discover its current flags at runtime. The verified `mmx vision describe` interface accepts an image path/URL or pre-uploaded file ID, plus a prompt; therefore the default adapter must sample keyframes rather than pass a full video. Do not treat `mmx video generate` as source-video analysis.

## Quality and safety

- Prefer false positives (extra seconds) over cutting off a rally.
- Never claim certainty; expose confidence and evidence.
- Do not overwrite the source video.
- Treat provider output as untrusted: validate all timestamps, scores, and JSON.
- Never interpolate model text into shell commands.

Read `references/scoring-model.md` for scoring changes, `references/provider-interface.md` for analyzer backends, and `references/review-schema.md` for HTML edits and rendering.

For agent handoff, current implementation status and known limitations are documented in `DEVELOPMENT.md`.
