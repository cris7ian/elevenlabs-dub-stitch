"""Thin wrappers around ffmpeg and ffprobe.

Locations can be pinned with the FFMPEG / FFPROBE / FFMPEG_FONTSDIR
environment variables; otherwise the binaries are looked up on PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .config import BAND_H, TOTAL_H, VIDEO_H, VIDEO_W


class MediaError(RuntimeError):
    """A missing binary or a failing ffmpeg/ffprobe command."""


def _binary(env_var: str, name: str) -> str:
    found = os.environ.get(env_var) or shutil.which(name)
    if not found:
        raise MediaError(f"{name} not found; install it or set ${env_var}")
    return found


def ffmpeg() -> str:
    return _binary("FFMPEG", "ffmpeg")


def ffprobe() -> str:
    return _binary("FFPROBE", "ffprobe")


def fontsdir() -> str:
    """Directory passed to libass so it can resolve the downloaded fonts."""
    return os.environ.get(
        "FFMPEG_FONTSDIR", str(Path.home() / ".local" / "share" / "fonts")
    )


def run(cmd: list[str], capture: bool = True) -> str:
    proc = subprocess.run(
        cmd, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-8:]
        raise MediaError(f"{cmd[0]} failed ({proc.returncode}): " + " | ".join(tail))
    return proc.stdout or ""


def duration(path: Path | str) -> float:
    out = run([ffprobe(), "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)])
    return float(out.strip().splitlines()[0])


def streams(path: Path | str) -> list[dict]:
    out = run([ffprobe(), "-v", "error", "-show_streams", "-of", "json", str(path)])
    return json.loads(out).get("streams", [])


def video_size(path: Path | str) -> tuple[int, int]:
    for stream in streams(path):
        if stream.get("codec_type") == "video":
            return int(stream["width"]), int(stream["height"])
    raise MediaError(f"no video stream in {path}")


def cut(src: Path | str, dest: Path | str, start: float = 0.0,
        seconds: float | None = None) -> Path:
    """Trim a clip with re-encoded video so the first frame is exact."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg(), "-y", "-v", "error", "-ss", f"{start}", "-i", str(src)]
    if seconds is not None:
        cmd += ["-t", f"{seconds}"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(dest)]
    run(cmd)
    return dest


def _escape_filter_path(path: Path | str) -> str:
    """Escape a path for use as a value inside an ffmpeg filtergraph."""
    text = str(path).replace("\\", "\\\\")
    return text.replace(":", r"\:").replace("'", r"\'")


def extract_audio(src: Path | str, dest: Path | str, codec: str = "flac") -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    run([ffmpeg(), "-y", "-v", "error", "-i", str(src),
         "-vn", "-c:a", codec, str(dest)])
    return dest


def mux(video: Path | str, audio: Path | str, dest: Path | str) -> Path:
    """Attach an audio track to a video without re-encoding the video."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    run([ffmpeg(), "-y", "-v", "error", "-i", str(video), "-i", str(audio),
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
         "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(dest)])
    return dest


def burn(video: Path | str, ass: Path | str, dest: Path | str, *,
         layout: str = "band", band_h: int = BAND_H) -> Path:
    """Render an .ass file onto the video, adding the title band if asked."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    ass_ref = _escape_filter_path(ass)
    fonts = _escape_filter_path(fontsdir())
    if layout == "band":
        chain = (f"pad={VIDEO_W}:{VIDEO_H + band_h}:0:{band_h}:color=0x0B0B10,"
                 f"ass={ass_ref}:fontsdir={fonts},setsar=1")
    else:
        chain = f"ass={ass_ref}:fontsdir={fonts},setsar=1"
    run([ffmpeg(), "-y", "-v", "error", "-i", str(video), "-vf", chain,
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
         str(dest)])
    return dest


def concat(parts: list[Path | str], dest: Path | str,
           listfile: Path | str | None = None) -> Path:
    """Stream-copy concatenation; every part must share codec and geometry."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    listfile = Path(listfile) if listfile else dest.with_suffix(".concat.txt")
    listfile.parent.mkdir(parents=True, exist_ok=True)
    listfile.write_text(
        "".join(f"file '{Path(p).resolve()}'\n" for p in parts), encoding="utf-8"
    )
    run([ffmpeg(), "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(listfile), "-c", "copy", "-movflags", "+faststart",
         str(dest)])
    return dest


__all__ = [
    "MediaError", "ffmpeg", "ffprobe", "fontsdir", "run", "duration", "streams",
    "video_size", "cut", "extract_audio", "mux", "burn", "concat", "TOTAL_H",
]
