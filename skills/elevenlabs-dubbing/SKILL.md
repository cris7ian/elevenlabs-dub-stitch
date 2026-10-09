---
name: elevenlabs-dubbing
description: "Use when dubbing a clip into other languages or captioning and stitching the dubs. Runs from this repo's dubstitch CLI."
version: 2.0.0
author: Cristian Caroli, Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Dubbing, ElevenLabs, STT, Audio, Video, Multilingual, Subtitles]
    related_skills: [youtube-content, ffmpeg-png-concat-pts]
---

# AI Voice Dubbing

## When to use

Use when the user wants a video or audio clip dubbed, translated, or spoken in
other languages by a hosted API (ElevenLabs and equivalents), and also when they
want those dubs captioned, stitched into one compilation, or both. The same
workflow covers a single-language dub and a batch of seven.

## The code lives in this repository

`dubstitch` implements the whole workflow and is the thing to run. Do not
re-derive it from the API docs.

```sh
cd ~/Developer/elevenlabs-dub-stitch        # or clone the repo
python3 -m pytest                           # offline, free, fast
python3 -m dubstitch fonts                  # CJK/Arabic fonts, no root
python3 -m dubstitch clip  "<url>" --duration 5          # free
python3 -m dubstitch submit --targets en,de,ja,fr,ar,ko,it   # BILLS
python3 -m dubstitch fetch                                # free
python3 -m dubstitch render --order es,en,de,ja,fr,ar,ko,it  # free
python3 -m dubstitch all "<url>" --duration 5             # all four
```

Only `submit` (and `all`) costs money. `fetch` and `render` are idempotent, so
iterate on captions and layout for free from the cached audio in `work/dubs/`.

Key resolution: `--api-key`, `$ELEVENLABS_API_KEY`, `./.elevenlabs_api_key`,
`~/.config/elevenlabs/api_key`, `./.env`. Never paste a key into a report, a
script or this skill.

Source of truth for the API details and the burn-in rules:
`references/elevenlabs-dubbing.md` and `references/subtitle-burn-in.md`.

## Deliverable shape

- **One stitched compilation**, not N loose files. Segment order: the original
  language first, then the dubs.
- Each segment sits under a solid title band naming the language — Latin name
  plus native spelling when they differ (`JAPANESE  ·  日本語`).
- House caption style: yellow (`&H0000FFFF`) with a heavy black border, 48 px on
  a 1280-wide frame. Keep the band and the captions on every segment so the
  compilation reads as one piece.
- Render ONE segment in the candidate layout and let the user pick before
  encoding the rest; a layout change means re-encoding everything.
- Report the spoken line per language by re-transcribing the delivered audio.
  Never report a translation from memory or from the user's guess.
- Send a contact sheet of one still per segment alongside the video.
- State the per-language billing. Each language is a separate charge, and
  creating a project charges one before any output exists.

## Procedure

1. **Cut the source clip.** `dubstitch clip URL --duration 5` — yt-dlp takes only
   the wanted range, then ffmpeg remuxes to mp4. Confirm the clip holds speech
   before paying: `ffmpeg -i clip.mp4 -af silencedetect=noise=-35dB:d=0.35 -f null -`.
2. **Submit.** `dubstitch submit --targets ...`. The first language is queued by
   the project create call and absorbs the minimum charge; the rest are added one
   at a time with a gap, retrying 429 with backoff.
3. **Fetch.** `dubstitch fetch` polls to `ready`, then to no target `queued` or
   `processing`, downloads `outputs.lossless_audio`, and muxes each dub back onto
   the source clip. Signed URLs expire in about an hour, so download in the same
   run that polls.
4. **Render.** `dubstitch render --layout band --order es,en,...` transcribes each
   *dubbed* audio (never the source transcript), builds cues, writes `.ass`,
   burns with libass, and concatenates.
5. **Verify, then deliver.** Pull every segment back out of the *stitched* file and
   re-transcribe it. Each slice must come back in its own language, in order. Also
   pull a frame per segment and look at it — rendering faults never appear in logs.

## Pitfalls

- A `401 missing_permissions` on one endpoint means the key lacks that scope, not
  that the key is wrong. `/v1/user` needs `user_read`; dubbing and speech-to-text
  usually work anyway. Probe the endpoint the task actually needs.
- The dubbing project API returns **audio only** (`outputs.lossless_audio`). Mux
  the video locally; do not wait for a video URL.
- Rapid sequential language-target POSTs return **429**. Serialize with a sleep and
  retry with backoff.
- Accumulated **characters**, not token count, decide where a cue splits. CJK
  speech-to-text returns one token per character, so a token cap slices Japanese
  mid-word.
- Join CJK transcripts with **no separator**, or every glyph gets a gap after it.
- Speech-to-text returns zero-length spans for a trailing interjection. Enforce a
  minimum on-screen time (~0.9 s) or that line never appears.
- Repeated transcriptions of the same audio **disagree on slang and nicknames**.
  Pin those lines to what the speaker actually says rather than accepting whichever
  spelling came back.
- Burning CJK or Arabic needs a font with the glyphs **and** `fontsdir` passed to
  the `ass` filter. Missing glyphs render as boxes with no error.
- A failed font download still writes a file. Check the status and the size, delete
  the 404s, and only then `fc-cache`.
- Do not judge RTL shaping from a thumbnail: correct Arabic reads as garbled at low
  resolution. Zoom the crop before calling it broken.
- Do not verify a concat by hashing decoded PCM at byte offsets — AAC priming and
  seek make identical audio hash differently.

## Reference and scripts

- `references/elevenlabs-dubbing.md` — endpoints, parameters, response shapes,
  model and language codes, error meanings, billing rules.
- `references/subtitle-burn-in.md` — cue rules, ASS values, the title-band layout,
  CJK/Arabic font handling, render and stitch checks.
- Runnable code: the `dubstitch` package in this repository, with 21 offline tests.
