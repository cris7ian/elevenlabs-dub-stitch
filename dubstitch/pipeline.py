"""End-to-end pipeline: clip -> submit -> fetch -> render.

The four stages are separate commands on purpose.

* ``submit`` is the only stage that spends money (ElevenLabs bills each language
  target, and a project creation bills a minimum of one).
* ``fetch`` and ``render`` are free to repeat, which is what makes the visual
  half of the pipeline cheap to iterate on and easy to test.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config, fonts, media, subtitles
from .elevenlabs_api import Client

ORIGINAL = config.ORIGINAL


@dataclass
class State:
    """What the pipeline remembers between commands."""

    project_id: str | None = None
    project_name: str | None = None
    source_language: str = ORIGINAL
    source_url: str | None = None
    source_clip: str | None = None
    model_id: str = config.MODEL_ID
    targets: dict[str, str] = field(default_factory=dict)
    order: list[str] = field(default_factory=lambda: list(config.LANGS))

    @classmethod
    def load(cls, path: Path | str) -> "State":
        path = Path(path)
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        known = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in data.items() if key in known})

    def save(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        return path


# ------------------------------------------------------------------- clip ----
def _ytdlp_command() -> list[str]:
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    try:
        import yt_dlp  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise media.MediaError("yt-dlp is not installed: pip install yt-dlp") from exc
    return [sys.executable, "-m", "yt_dlp"]


def download_clip(
    url: str, dest: Path | str, *, start: float = 0.0, seconds: float = 5.0,
    log=print,
) -> Path:
    """Download just the wanted slice of a video and remux it to mp4."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    section = f"*{start}-{start + seconds}"
    log(f"  yt-dlp section {section}")
    media.run(_ytdlp_command() + [
        "--no-warnings", "--no-playlist", "--force-keyframes-at-cuts",
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
        "--download-sections", section,
        "-o", str(dest.with_suffix(".%(ext)s")), url,
    ])
    produced = [p for p in sorted(dest.parent.glob(dest.stem + ".*")) if p != dest]
    if not produced:
        raise media.MediaError(f"yt-dlp produced no media for {url}")
    media.run([media.ffmpeg(), "-y", "-v", "error", "-i", str(produced[0]),
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart", str(dest)])
    for extra in produced:
        extra.unlink(missing_ok=True)
    log(f"  clip -> {dest}")
    return dest


# ----------------------------------------------------------------- submit ----
def submit(
    client: Client,
    state: State,
    *,
    source: Path | str | None = None,
    source_url: str | None = None,
    source_language: str | None = None,
    targets: list[str] | None = None,
    name: str | None = None,
    pause: float = 3.0,
    log=print,
) -> State:
    """Create the dubbing project and queue every language target.

    The first target is created with the project (it absorbs the minimum
    charge); the rest are added afterwards, spaced out to stay under the
    per-workspace rate limit.
    """
    source_language = source_language or state.source_language
    wanted = list(targets or [t for t in config.LANGS if t != source_language])
    wanted = [lang for lang in wanted if lang != source_language]
    if not wanted:
        raise ValueError("no target languages to dub")

    first, rest = wanted[0], wanted[1:]
    log(f"  creating project (bills a minimum of one language: {first})")
    project = client.create_project(
        source=source,
        source_url=source_url,
        source_language=source_language,
        target_language=first,
        reference=name,
    )
    state.project_id = project["project_id"]
    state.project_name = name
    state.source_language = source_language
    state.model_id = project.get("model_id") or state.model_id
    if source:
        state.source_clip = str(Path(source).resolve())
    if source_url:
        state.source_url = source_url
    language_ids = project.get("language_ids") or [None]
    state.targets = {first: language_ids[0]}
    log(f"  project {state.project_id} (model {state.model_id})")

    client.wait_for_project(state.project_id, log=log)

    for lang in rest:
        row = client.add_target(state.project_id, lang)
        state.targets[lang] = row.get("language_id")
        log(f"  queued {lang} -> {row.get('language_id')}")
        time.sleep(pause)
    return state


# ------------------------------------------------------------------ fetch ----
def fetch(client: Client, state: State, workdir: Path | str, *, log=print) -> list[str]:
    """Wait for the targets, download the dub audio, mux it back onto the clip."""
    workdir = Path(workdir)
    dubs, clips = workdir / "dubs", workdir / "clips"
    dubs.mkdir(parents=True, exist_ok=True)
    clips.mkdir(parents=True, exist_ok=True)

    if not state.project_id:
        raise ValueError("no project id in the state file; run `submit` first")
    rows = client.wait_for_targets(state.project_id, log=log)
    clip = Path(state.source_clip) if state.source_clip else None

    downloaded: list[str] = []
    for row in rows:
        lang, status = row["target_language"], row["status"]
        if status != "completed":
            message = (row.get("error") or {}).get("message", "")
            log(f"  !! {lang} is {status} {message}".rstrip())
            continue
        url = (row.get("outputs") or {}).get("lossless_audio")
        if not url:
            log(f"  !! {lang} produced no audio output")
            continue
        dest = client.download(url, dubs / f"{lang}.flac")
        if clip and lang != state.source_language:
            media.mux(clip, dest, clips / f"{lang}.mp4")
        downloaded.append(lang)
        log(f"  {lang}: {dest.name} ({dest.stat().st_size:,} bytes)")

    if clip:
        original = dubs / f"{state.source_language}.flac"
        if not original.exists():
            media.extract_audio(clip, original)
        log(f"  {state.source_language}: {original.name} (extracted from the clip)")
    return downloaded


# ----------------------------------------------------------------- render ----
def render(
    state: State,
    workdir: Path | str,
    *,
    layout: str = "band",
    order: list[str] | None = None,
    client: Client | None = None,
    log=print,
) -> Path:
    """Subtitle each segment, burn the subtitles in, and concatenate."""
    workdir = Path(workdir)
    dubs, clips, renders = workdir / "dubs", workdir / "clips", workdir / "renders"
    ass_dir = renders / "ass"
    renders.mkdir(parents=True, exist_ok=True)

    installed = fonts.ensure(log=log)
    client = client or Client(workdir=workdir)
    order = list(order or state.order)

    segments: list[Path] = []
    for lang in order:
        audio = dubs / f"{lang}.flac"
        if lang == state.source_language and state.source_clip:
            video = Path(state.source_clip)
        else:
            video = clips / f"{lang}.mp4"
        if not audio.exists() or not video.exists():
            log(f"  skip {lang}: missing {audio.name if not audio.exists() else video.name}")
            continue

        words, text = client.transcribe_words(audio)
        cues = subtitles.build_cues(words, lang)
        document = subtitles.ass_document(lang, cues, media.duration(video), layout)
        ass_path = subtitles.write_ass(ass_dir / f"{lang}.ass", document)
        segment = media.burn(video, ass_path, renders / f"seg_{layout}_{lang}.mp4",
                             layout=layout)
        log(f"  {lang}: {len(cues)} cue(s) — {text}")
        for start, end, cue in cues:
            log(f"      {start:5.2f}-{end:5.2f}  {cue.replace(chr(92) + 'N', ' / ')}")
        segments.append(segment)

    if not segments:
        raise media.MediaError("nothing to render; run `fetch` first")
    if len(segments) == 1:
        return segments[0]
    stitched = media.concat(segments, renders / f"stitched_{layout}.mp4")
    log(f"  stitched -> {stitched} ({media.duration(stitched):.2f}s)")
    return stitched
