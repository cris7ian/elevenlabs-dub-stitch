# Subtitles and the stitched compilation

This is the stage after the dubs exist: transcribe each dubbed audio, burn
captions, stitch one compilation. Do it with the `ass` filter; do not hand-roll
`drawtext` per line, and do not try to chain per-word overlays.

The numbers below are the defaults in `dubstitch/config.py`. Change them there,
not in a generated `.ass` — regeneration overwrites hand edits.

## Segments and the title band

Prefer a band above the clip over overlaying the label on the frame whenever the
source already has burned-in graphics along its top edge; an overlay collides with
them and looks like a mistake.

- Pad the clip into a taller frame and park the band in the new space:
  `pad=1280:812:0:92:color=0x0B0B10` puts the clip at y=92 with a 92 px band above.
- A 92 px band centres a 52 px header. For top alignment `MarginV` is measured from
  the frame top, so `MarginV ≈ (band_height - line_height) / 2 ≈ 15`.
- `PlayResY` must equal the PADDED frame height (812), not the clip height (720).
  A mismatch rescales every margin and misplaces the header.
- Captions stay bottom-centred against the padded frame (`MarginV 34`), so they sit
  over the clip's own lower area. That is intended.

## ASS values that matter

- Colours are `&HAABBGGRR`, alpha `00` opaque. Yellow `&H0000FFFF`, black
  `&H00000000`. Writing RRGGBB instead silently yields blue text.
- `Alignment` 8 = top centre, 2 = bottom centre.
- `BorderStyle 1` plus `Outline` draws a border around the glyphs. `BorderStyle 3`
  draws an opaque box behind the text in the outline colour — right for a label
  sitting on the frame, unnecessary inside the label's own band.
- Bigger captions want a thicker border, not a shadow: size 48 with `Outline 6`
  stays legible over busy footage.
- `ScaledBorderAndShadow: yes` so a non-default `PlayRes` does not change the look.
- Write the file as UTF-8. RTL scripts (Arabic, Hebrew, Persian, Urdu) need a font
  that has the glyphs; libass does bidi and shaping itself. `\q2` in the dialogue
  text suppresses wrapping if a line must stay whole.
- Fade the header in and out, `{\fad(200,200)}`, so consecutive segments do not
  hard-cut into one another.

## Cue building from word timings

Request word granularity (`timestamps_granularity=word`) from speech-to-text, then:

- Split a cue on a pause of about 0.30 s or more.
- Cap a cue by accumulated CHARACTERS (`max_chars * max_lines`, e.g. 30 x 2). Never
  cap by token count: CJK returns one token per character, so a token cap cuts
  Japanese mid-word.
- Join tokens with a space for languages that use them, and with `""` for `ja`,
  `zh`, `yue`, `cmn`.
- Enforce a minimum on-screen time (~0.9 s) and clamp the end to the clip duration.
  A trailing interjection often arrives with start == end and would never show.
- Start a cue ~0.06 s early and hold it ~0.35 s past the last word.
- Re-read the generated captions from a still before rendering all segments.

## Pinning a line

When the speech is slang, a nickname, or something the model keeps re-hearing
differently, pin that language's line to what the speaker actually says. In this
repo that is `config.MANUAL_CUE`, a `{lang: text}` map that keeps the timestamp
range from the word timings and replaces only the text. Set it to `{}` to always
trust the transcriber. Never hand-edit a generated `.ass` — regeneration
overwrites it.

## Fonts

The `ass` filter resolves families through fontconfig. Latin usually resolves to
whatever is installed; CJK and Arabic usually are not.

- Check first: `fc-list --format '%{family[0]}\n' | grep -i 'noto sans'`.
- Install per user with no sudo: download the font into
  `~/.local/share/fonts/<subdir>/`, then `fc-cache -f ~/.local/share/fonts`.
  The Google Fonts mirror is the path verified to work, e.g.
  `https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf`,
  same shape for `notosanskr` and `notosansarabic`. Verify the download: a 404 still
  writes a file of a few hundred KB, so check the HTTP status and the size and
  delete the failures before `fc-cache`, or the family silently will not resolve.
- Pass the directory to the filter:
  `-vf "pad=...,ass=subs.ass:fontsdir=$HOME/.local/share/fonts"`.
- Family names as fontconfig reports them: `Noto Sans JP`, `Noto Sans KR`,
  `Noto Sans Arabic`, `Liberation Sans` for Latin. Variable fonts resolve to their
  Regular instance and render fine.
- `fc-list`'s default output is `<file>: <family>`, so parse with an explicit
  `--format '%{family[0]}\n'`. Splitting the default format on commas leaves the
  file path glued to the family name and nothing ever matches.
- Set the style font per language. One family per segment is enough: the header is
  Latin, and every Noto CJK family also covers Latin.
- Another non-Latin script needs its own Noto family fetched the same way, and its
  family name added to the font map.

## Verify the render, then verify the stitch

- Still per segment: `ffmpeg -ss T -i out.mp4 -frames:v 1 f.png`. Tile them into one
  contact sheet with
  `-vf "scale=760:482,tile=2x4:margin=8:padding=8:color=0x2b2b2b"`.
- Check each still for: label present, caption inside the frame, caption not broken
  mid-word, glyphs drawn rather than boxed.
- Zoom before judging Arabic or any RTL line:
  `crop=1280:150:0:662,scale=1707:200`. Correct shaping reads as garbled at
  thumbnail resolution.
- Then verify the compilation itself: extract each segment from the STITCHED file
  and re-transcribe it. Each slice must come back in its own language, in order.
  This is the check that proves order and audio alignment end to end.
- Do not verify a concat by hashing decoded PCM at byte offsets. AAC priming and
  seek make identical audio hash differently, so a matching hash failure proves
  nothing.
