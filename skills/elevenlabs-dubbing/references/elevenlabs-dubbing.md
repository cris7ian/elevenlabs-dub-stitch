# ElevenLabs dubbing — API notes

Base URL: `https://api.elevenlabs.io/v1`. Auth header: `xi-api-key: <key>`.

Docs: `https://elevenlabs.io/docs/api-reference/dubbing/create-project`,
`.../dubbing/language-targets/create-language-target`,
`.../help-center/product/dubbing/which-languages-are-supported-in-dubbing`.
Append `.md` to any docs URL for the markdown version.

## Endpoints

| Step | Call |
| --- | --- |
| Create project | `POST /v1/dubbing/project` (multipart) |
| Project state | `GET /v1/dubbing/project/{project_id}` |
| Add language | `POST /v1/dubbing/project/{project_id}/language` (JSON) |
| List languages | `GET /v1/dubbing/project/{project_id}/language` |
| Transcribe | `POST /v1/speech-to-text` (multipart, `model_id=scribe_v1`) |
| Legacy single dub | `POST /v1/dubbing` |
| List old dubs | `GET /v1/dubbing?page_size=N` |

## Create project — fields

- `file` or `source_url` — one of the two, not both. Media up to 3 GiB.
- `source_language` — BCP-47 tag. Omit to auto-detect; set it when you know it.
- `model_id` — `dubbing_v1` or `dubbing_v2`. Default `dubbing_v2`. Fixed at create
  time; no later change.
- `reference` — free-form, <= 500 chars, echoed back.
- `target_language` — optional shortcut that also queues the first language
  target; its id comes back in `language_ids`. Consumes the minimum charge.
- `keyterms` — bias terms, <= 1000 entries, <= 50 chars and 5 words each.
- `webhook_ids` — up to 3 workspace webhook ids; the recommended alternative to
  polling. Events: `dubbing_project_ready`, `dubbing_project_failed`,
  `dubbing_language_completed` (carries output URLs), `dubbing_language_failed`.
- `transcript` — Enterprise only, bring your own transcript.

Response: `project_id`, `status`, `language_ids`, `media`, `model_id`, `revision`.

Project status values: `queued`, `preparing`, `processing`, `ready`, `failed`.

## Add language — fields

- `target_language` (required) — BCP-47, e.g. `fr`, `es-MX`, `ar-EG`.
- `voice_settings` — applies to every speaker in that language.
- `translations` — Enterprise only.

Language target status values: `queued`, `processing`, `completed`, `stale`,
`failed`. `stale` means the transcript changed after the output was produced.

## Output shape

```json
{"languages":[{"language_id":"...","target_language":"en","status":"completed",
  "outputs":{"lossless_audio":"https://storage.googleapis.com/.../output.flac?X-Goog-..."},
  "output_revision":0,"revision":0,"error":null}]}
```

- Output key is `outputs.lossless_audio` (signed FLAC, expires in about an hour).
  There is no video key: mux the video locally.
- The list wrapper is `languages`. Older responses used `language_targets`.
- Signed URLs expire, so download in the same run that polls. Re-fetch the
  language list to get fresh URLs.

## Speech to text

`POST /v1/speech-to-text`, multipart, `model_id=scribe_v1`, optional
`timestamps_granularity=word`. The response carries `text`, `language_code`,
`language_probability`, and a `words` array of `{text, start, end, type}` where
`type` is `word` or `spacing`. Filter to `word` before building cues.

CJK output is one token per character — see `subtitle-burn-in.md` before writing
any cue logic against it.

## Language codes (common)

`en` (`en-US`, `en-GB`, `en-AU`, `en-CA`), `de`, `ja`, `fr` (`fr-FR`, `fr-CA`),
`ar` (`ar-EG`), `ko`, `it`, `es` (`es-ES`, `es-MX`, `es-AR`, `es-CL`), `pt`
(`pt-BR`, `pt-PT`), `zh` (`zh-TW`), `hi`, `ru`, `nl`, `pl`, `tr`, `sv`, `da`,
`fi`, `no`, `cs`, `el`, `he`, `uk`, `vi`, `th`, `id`, `fa`, `ur`, `yue`, `cmn`.

Dubbing v1 supports base tags only; v2 accepts the listed dialects. A language
absent from the docs list is rejected, not silently substituted.

## Errors seen in practice

- `401 authentication_error` / `missing_permissions` — the key lacks that scope.
  `GET /v1/user` needs `user_read`, which restricted keys often do not carry.
  `GET /v1/voices`, `/v1/dubbing`, and `/v1/speech-to-text` commonly work anyway.
- `429` on target creation — rate limit. Space out the POSTs and retry.
- `422 unprocessable_entity` — malformed or unsupported field, for example a
  language code outside the model's list.

## Billing

- Creating a project charges a minimum of one language, before any output exists.
- Each additional language target is charged separately, at creation time.
- Seven languages means seven generations. Confirm the list before queueing.
