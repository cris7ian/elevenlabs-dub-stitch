# AGENTS.md

Guidance for coding agents working in this repository.

## What this is

`dubstitch` dubs a short clip into several languages via the ElevenLabs Dubbing
project API, burns subtitles into each version, and stitches them into one file.
User-facing documentation is in [README.md](README.md); the agent-facing skill is
in [skills/elevenlabs-dubbing/](skills/elevenlabs-dubbing/SKILL.md).

## Architecture

Four stages, deliberately separate commands:

1. `clip` — yt-dlp downloads only the wanted time range; ffmpeg remuxes to mp4.
2. `submit` — creates the ElevenLabs project and queues language targets.
3. `fetch` — polls, downloads `outputs.lossless_audio`, muxes it onto the clip.
4. `render` — scribe word timings → cues → ASS → burn with libass → concat.

Module boundaries worth preserving:

- `config.py` holds every tunable number, colour and language table.
- `elevenlabs_api.py` is the only module that talks to the network.
- `subtitles.py` is pure — no I/O, no shared state, trivially testable.
- `media.py` is the only module that shells out to ffmpeg.
- `pipeline.py` orchestrates and owns `work/state.json`.
- `cli.py` parses arguments and nothing else.

## Commands

```sh
python3 -m pytest                     # offline unit tests
python3 -m dubstitch fonts            # install CJK/Arabic fonts
python3 -m dubstitch render           # regenerate subtitles + stitch (free)
python3 -m dubstitch render --layout overlay
make help
```

## Hard rules

1. **Never commit secrets or media.** `.env`, `.elevenlabs_api_key` and `work/`
   are gitignored. Keep them that way. The demo clip is third-party content.
2. **Never call `submit` (or `all`) in tests or in an automated check.** It creates
   real ElevenLabs projects and bills per language. The test suite must stay
   offline — `pytest` makes zero network calls.
3. **Iterate with `render`, not `all`.** Cached dub audio under `work/dubs/` makes
   subtitle and layout work free and instant. Only go back to `submit` when the
   source clip or the target language list actually changes.
4. **Standard library only for runtime code.** `yt-dlp` is the single external
   dependency; `pytest` is dev-only. Do not add `requests`, `pydub`, and friends.
5. **Keep `subtitles.py` pure.** Anything needing a key, a file or a subprocess
   belongs in `pipeline.py` or `media.py`.

## Pitfalls that already bit us

- **The project API returns audio only.** `outputs.lossless_audio` is a signed
  FLAC; there is no dubbed video. Video always comes from the local clip via
  `media.mux`. The URLs expire in about an hour — download in the run that polls.
- **Target creation is rate limited.** A burst of `POST .../language` calls returns
  429. `add_target` retries with backoff; the pipeline also pauses between targets.
- **Scribe tokenises Japanese per character.** Join those languages with no
  separator, and budget cue splitting in *characters*, never in token count, or a
  phrase gets split mid-word.
- **Very short utterances can come back with zero duration** (start == end).
  `CUE_MIN_DURATION` keeps them on screen.
- **Repeated transcriptions disagree on slang.** That is why `config.MANUAL_CUE`
  exists; pin the line instead of accepting whichever spelling came back.
- **`fc-list` prints `<file>: <family>` by default.** Parse with
  `--format '%{family[0]}\n'`, or the file path glues itself to the family name and
  no font ever matches.
- **libass needs real fonts.** CJK and Arabic render as boxes without Noto.
  `dubstitch.fonts.ensure()` runs from `render` for that reason.
- **`ass=` in an ffmpeg filtergraph** needs the path escaped; use
  `media._escape_filter_path` rather than interpolating a path directly.
- **Empty `work/` on a clean clone is expected.** `render` skips a language whose
  audio or clip is missing instead of failing the whole run.
- **Do not verify a concat by hashing decoded PCM at offsets.** AAC priming and
  seek make identical audio hash differently. Extract each segment and
  re-transcribe it instead.

## Verifying a change

```sh
python3 -m pytest                                  # logic
python3 -m dubstitch render --layout band          # if work/dubs is populated
ffprobe -v error -select_streams v:0 \
    -show_entries stream=width,height -show_entries format=duration \
    -of default=nw=1 work/renders/stitched_band.mp4
```

For a subtitled-media change, extract a frame at the timestamp you care about and
look at it — text rendering faults (clipping, missing glyphs, RTL order) never
appear in logs:

```sh
ffmpeg -y -ss 17.5 -i work/renders/stitched_band.mp4 -frames:v 1 /tmp/frame.png
```

## Style

- Comments explain *why*, not *what*. Do not narrate the code.
- Keep the STE-inspired tone of the existing docs: short sentences, active voice,
  one idea per line.
- No AI attribution in commits, comments or documentation.
