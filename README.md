# dubstitch

Take a few seconds of video and get the same few seconds back in eight
languages, subtitled, in one file.

It cuts a clip, asks ElevenLabs to dub it into every target language, writes
yellow subtitles from the *dubbed* audio, names each segment in a title band,
and concatenates the lot.

## What the output looks like

Eight 5-second segments, one after another, 1280x812:

```
┌──────────────────────────────────────────────┐
│            JAPANESE  ·  日本語                │  ← title band
├──────────────────────────────────────────────┤
│                                              │
│                (the clip)                    │
│                                              │
│   おい、何なんだよ、このぐうたら野郎は。あ？      │  ← yellow, black border
└──────────────────────────────────────────────┘
```

The source language comes first and is the untouched original audio, so the
result doubles as a reference track.

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` on `PATH` (any recent build with `libass`)
- `yt-dlp` — `pip install -r requirements.txt`
- An ElevenLabs API key with **Dubbing** and **Speech to Text** permissions

Nothing else. The ElevenLabs client is standard library only.

## Install

```sh
git clone https://github.com/cris7ian/elevenlabs-dub-stitch.git
cd elevenlabs-dub-stitch
pip install -r requirements.txt          # or: pip install -e '.[dev]'

export ELEVENLABS_API_KEY=sk_...          # or: cp .env.example .env
./scripts/install-fonts.sh                # CJK + Arabic fonts, no root needed
make test                                 # offline tests, no API calls
```

## Use

One command, video to finished file:

```sh
python3 -m dubstitch all "https://youtu.be/Bs6ev0utXbs" \
    --duration 5 \
    --targets en,de,ja,fr,ar,ko,it \
    --layout band
# -> work/renders/stitched_band.mp4
```

Or drive the four stages yourself. This is the better habit: only the second
stage costs money, so you can re-cut and re-render as often as you like.

```sh
python3 -m dubstitch clip  "https://youtu.be/..." --duration 5   # free
python3 -m dubstitch submit --targets en,de,ja,fr,ar,ko,it       # BILLS
python3 -m dubstitch fetch                                       # free
python3 -m dubstitch render --order es,en,de,ja,fr,ar,ko,it      # free
```

`fetch` and `render` are idempotent — re-running `render` after tweaking
`dubstitch/config.py` regenerates the subtitles and the stitch without spending
anything.

### Commands

| Command | What it does | Cost |
| --- | --- | --- |
| `fonts` | Installs the CJK/Arabic fonts libass needs into `~/.local/share/fonts` | free |
| `clip URL` | yt-dlp downloads only `--start .. --start+--duration` and remuxes to mp4 | free |
| `submit` | Creates the ElevenLabs dubbing project and queues every language target | **billed per language** |
| `fetch` | Waits for the dubs, downloads the lossless audio, muxes it onto the clip | free |
| `render` | Transcribes each dub, burns subtitles, concatenates | free |
| `all URL` | All of the above | **billed** |

Global flags: `--workdir` (default `./work`), `--state`, `--api-key`.

## Cost

ElevenLabs bills **per language target**, and creating a project charges a
minimum of one language before any output exists. The default target list is
seven languages, plus the free original: eight segments, seven charges. Check
current pricing before running `all` on a long clip.

## How it works

```
clip ──> submit ──> fetch ──> render
 │         │          │         │
 │         │          │         └─ scribe word timings -> cues -> .ass ->
 │         │          │            burn with libass -> concat
 │         │          └─ poll targets, download lossless_audio,
 │         │             mux dub audio back onto the source video
 │         └─ POST /v1/dubbing/project, then one language target per language
 └─ yt-dlp --download-sections + ffmpeg remux
```

The Dubbing project API returns **audio only** (`outputs.lossless_audio`), so
the video track always comes from the local clip and gets muxed with ffmpeg.

Subtitles are generated from the *dubbed* audio, not the original, so cue
timings line up with the voice you actually hear. Word timings come from
`scribe_v1`; `dubstitch/subtitles.py` groups them into cues and renders ASS.

## Reproducibility

| Deterministic | Not deterministic |
| --- | --- |
| Cue grouping and ASS layout (pure functions, unit-tested) | Translation wording |
| Font selection via fontconfig + pinned Noto families | Voice chosen per speaker |
| Segment order, clip boundaries, container settings | Scribe's text on slurred or invented words |

The one place transcription instability showed up in the demo is pinned in
`config.MANUAL_CUE`, so the original-language subtitle is stable across runs.
Set `MANUAL_CUE = {}` to always trust the transcriber.

Everything expensive is cached under `work/`, which is gitignored: the source
clip, the dub audio, and the renders. Deleting `work/renders` costs nothing.

## Layout

```
dubstitch/
  config.py           layout, styling, languages, cue shaping — tweak here first
  elevenlabs_api.py   stdlib REST client: dubbing projects + scribe
  media.py            ffmpeg/ffprobe wrappers (cut, mux, burn, concat)
  subtitles.py        pure cue shaping and ASS generation
  fonts.py            on-demand Noto JP/KR/Arabic installer
  pipeline.py         clip -> submit -> fetch -> render, plus the state file
  cli.py              argparse front end
tests/                offline tests; no network, no API calls
skills/               agent skill describing this workflow (repo-scoped, not installed)
work/                 gitignored scratch: source, dubs, clips, renders
```

## Troubleshooting

**`401 ... missing_permissions: user_read`** — your key is scoped down. That
endpoint is not used by this tool; dubbing and speech-to-text are what matter.
Test with `python3 -m dubstitch fonts` (no key needed) and then a `submit`.

**`429` when queueing targets** — dubbing project target creation is rate
limited per workspace. `add_target` retries with backoff; if you still hit it,
raise the `pause` argument to `pipeline.submit`.

**CJK or Arabic renders as boxes** — libass cannot find the font. Run
`./scripts/install-fonts.sh`, and make sure `FFMPEG_FONTSDIR` (default
`~/.local/share/fonts`) is where they landed.

**Japanese subtitles have gaps between characters** — scribe tokenises Japanese
per character. Languages in `config.SPACELESS` join tokens with no separator.

**Subtitles split a word in half** — cue splitting is budgeted in characters,
not tokens. If you change `CUE_MAX_CHARS`, keep an eye on
`test_per_character_tokens_are_not_split_mid_word`.

## Notes on the demo clip

The reference run uses the first five seconds of
[cOño qUe mAnGuAnGuA vaLe](https://youtu.be/Bs6ev0utXbs). That clip belongs to
its uploader and is deliberately **not** committed here — `work/` is ignored so
nothing third-party or billed ever lands in the repository.

## License

MIT. See [LICENSE](LICENSE).
