---
name: elevenlabs-dubbing
description: "Use when dubbing video/audio into many languages via ElevenLabs. Clip, dub, subtitle, stitch — this repo has runnable code."
version: 1.0.0
author: Cristian Caroli, Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [ElevenLabs, Dubbing, Subtitles, ffmpeg, Media]
    related_skills: [ffmpeg-png-concat-pts, youtube-content]
---

# ElevenLabs Dubbing Pipeline

## When to use

Use when the user wants one piece of media dubbed into several languages, wants
subtitles burned into dubbed audio, or wants several language versions stitched
into a single comparison video. Also load this when an ElevenLabs dubbing call
misbehaves — the pitfalls below cover the failures that are not obvious from the
API docs.

## The code lives in a repository

`~/Developer/elevenlabs-dub-stitch` — a working implementation of this whole
workflow. Prefer running it over rewriting it:

```sh
cd ~/Developer/elevenlabs-dub-stitch
python3 -m dubstitch clip  "<url>" --duration 5    # free
python3 -m dubstitch submit --targets en,de,ja,fr,ar,ko,it   # BILLS
python3 -m dubstitch fetch                          # free
python3 -m dubstitch render --order es,en,de,ja,fr,ar,ko,it  # free
python3 -m dubstitch all "<url>" --duration 5       # all four
python3 -m pytest                                   # offline tests
```

Key resolution order: `--api-key`, `$ELEVENLABS_API_KEY`,
`./.elevenlabs_api_key`, `~/.config/elevenlabs/api_key`, `./.env`.

## Workflow

1. **Clip.** `yt-dlp --download-sections "*0-5" --force-keyframes-at-cuts`, then
   remux to mp4. A 5-second API request is far cheaper than a 55-second one.
2. **Submit.** `POST /v1/dubbing/project` with the file and the first
   `target_language`. Then `POST /v1/dubbing/project/{id}/language` per extra
   language.
3. **Poll.** `GET /v1/dubbing/project/{id}/language` → `.languages[].status`.
   `completed` when the output exists; the audio URL is `.outputs.lossless_audio`.
4. **Subtitle.** `POST /v1/speech-to-text` with `model_id=scribe_v1` on the
   *dubbed* audio, so timings match the voice actually heard.
5. **Render.** Build ASS, burn with `ass=` + `fontsdir=`, concat with the
   concat demuxer (`-c copy`).

## Pitfalls

- **Dubbing projects return audio only.** No video output. Mux the FLAC onto
  the local source clip yourself.
- **HTTP 429 on language-target creation.** Rate limited per workspace. Space
  the calls, retry with backoff.
- **Creating a project bills a minimum of one language** before any output
  exists, and each extra language bills separately. Never call submit in a loop
  or in a test.
- **Japanese scribe output is per-character.** Join with `""`, and never split
  cues by token count — split by character budget.
- **One-word cues can return `start == end`** and are invisible. Enforce a
  minimum cue duration.
- **libass needs real fonts.** CJK and Arabic need Noto (`~/.local/share/fonts`
  is enough, no root). Pass `fontsdir=` to the `ass` filter.
- **`\q2` for RTL** in the ASS dialogue line. Bidi itself works in libass once
  the font is present.
- **A scoped key may 401 on `/v1/user`** while dubbing works fine. Test the
  endpoints you actually use, not `/v1/user`.

## Verifying the result

Transcribe each segment back out of the finished file — this catches wrong
segment order and misaligned audio, which no log will show:

```sh
ffmpeg -y -ss 15.05 -t 5 -i stitched.mp4 -vn -c:a flac /tmp/seg.flac
curl -s -H "xi-api-key: $KEY" -F file=@/tmp/seg.flac -F model_id=scribe_v1 \
  https://api.elevenlabs.io/v1/speech-to-text | jq -r .text
```

Also pull a frame per segment and look at it; text rendering bugs (clipping,
missing glyphs, reversed RTL) never appear in logs.
