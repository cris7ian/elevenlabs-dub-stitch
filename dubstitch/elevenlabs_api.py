"""ElevenLabs REST client for dubbing projects and scribe transcription.

Standard library only — no `requests` dependency, so the tool runs anywhere a
Python 3.10+ interpreter does.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from .config import MODEL_ID, STT_MODEL

API_BASE = "https://api.elevenlabs.io/v1"
KEY_ENV = "ELEVENLABS_API_KEY"

_CONTENT_TYPES = {
    ".mp4": "video/mp4", ".mkv": "video/x-matroska", ".mov": "video/quicktime",
    ".webm": "video/webm", ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".flac": "audio/flac", ".m4a": "audio/mp4",
}


class ElevenLabsError(RuntimeError):
    """A non-2xx response or a transport failure."""


def resolve_api_key(explicit: str | None = None, workdir: Path | str | None = None) -> str:
    """Locate the API key: explicit argument, env var, then the usual files."""
    if explicit:
        return explicit.strip()
    if os.environ.get(KEY_ENV):
        return os.environ[KEY_ENV].strip()

    candidates: list[Path] = []
    if workdir:
        candidates += [Path(workdir) / ".elevenlabs_api_key", Path(workdir) / ".env"]
    candidates += [
        Path.home() / ".config" / "elevenlabs" / "api_key",
        Path.cwd() / ".elevenlabs_api_key",
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".elevenlabs_api_key",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        if "=" in text:                       # .env style
            for line in text.splitlines():
                line = line.strip()
                if line.startswith(f"{KEY_ENV}="):
                    return line.split("=", 1)[1].strip().strip("'\"")
            continue
        return text.strip()
    raise ElevenLabsError(
        f"no API key found; set {KEY_ENV}, or write it to ./.elevenlabs_api_key"
    )


def _content_type(path: Path) -> str:
    return _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def encode_multipart(
    fields: dict[str, str], files: list[tuple[str, Path]] | None = None
) -> tuple[bytes, str]:
    """Build a multipart/form-data body. Repeated field names stay repeated."""
    boundary = "----dubstitch" + uuid.uuid4().hex
    out = bytearray()
    for name, value in fields.items():
        out += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode("utf-8")
    for name, raw_path in files or []:
        path = Path(raw_path)
        out += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; '
            f'filename="{path.name}"\r\n'
            f"Content-Type: {_content_type(path)}\r\n\r\n"
        ).encode("utf-8")
        out += path.read_bytes() + b"\r\n"
    out += f"--{boundary}--\r\n".encode("utf-8")
    return bytes(out), f"multipart/form-data; boundary={boundary}"


class Client:
    """Thin wrapper over the endpoints this pipeline needs."""

    def __init__(
        self,
        api_key: str | None = None,
        workdir: Path | str | None = None,
        timeout: int = 180,
    ) -> None:
        self.api_key = resolve_api_key(api_key, workdir)
        self.timeout = timeout

    # ------------------------------------------------------------ plumbing --
    def _call(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        content_type: str | None = None,
        expect: tuple[int, ...] = (200, 201),
    ) -> dict:
        url = path if path.startswith("http") else f"{API_BASE}{path}"
        headers = {"xi-api-key": self.api_key}
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw, status = response.read(), response.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise ElevenLabsError(f"{method} {path} -> HTTP {exc.code}: {detail[:400]}") from exc
        except urllib.error.URLError as exc:
            raise ElevenLabsError(f"{method} {path} -> {exc.reason}") from exc
        if status not in expect:
            raise ElevenLabsError(f"{method} {path} -> HTTP {status}")
        return json.loads(raw) if raw else {}

    # ---------------------------------------------------- dubbing projects --
    def create_project(
        self,
        *,
        source_language: str | None = None,
        target_language: str | None = None,
        source: Path | str | None = None,
        source_url: str | None = None,
        model_id: str = MODEL_ID,
        reference: str | None = None,
        keyterms: list[str] | None = None,
    ) -> dict:
        """Create a dubbing project. Bills a minimum of one language target."""
        fields: dict[str, str] = {"model_id": model_id}
        if source_language:
            fields["source_language"] = source_language
        if target_language:
            fields["target_language"] = target_language
        if reference:
            fields["reference"] = reference
        if source_url:
            fields["source_url"] = source_url
        for term in keyterms or []:
            fields.setdefault("keyterms", term)
        files = [("file", Path(source))] if source else []
        body, content_type = encode_multipart(fields, files)
        return self._call("POST", "/dubbing/project", body, content_type)

    def project(self, project_id: str) -> dict:
        return self._call("GET", f"/dubbing/project/{project_id}")

    def targets(self, project_id: str) -> list[dict]:
        payload = self._call("GET", f"/dubbing/project/{project_id}/language")
        return payload.get("languages", [])

    def add_target(
        self,
        project_id: str,
        lang: str,
        *,
        retries: int = 6,
        backoff: float = 8.0,
        sleep=time.sleep,
    ) -> dict:
        """Queue one language target. Retries on the 429 rate limit."""
        body = json.dumps({"target_language": lang}).encode("utf-8")
        error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                return self._call(
                    "POST",
                    f"/dubbing/project/{project_id}/language",
                    body,
                    "application/json",
                )
            except ElevenLabsError as exc:
                error = exc
                if "HTTP 429" not in str(exc) or attempt == retries:
                    raise
                sleep(backoff)
        raise error  # pragma: no cover - the loop either returns or raises

    def wait_for_project(
        self, project_id: str, *, timeout: float = 900, interval: float = 5,
        sleep=time.sleep, log=print,
    ) -> dict:
        deadline = time.time() + timeout
        while True:
            state = self.project(project_id)
            status = state.get("status")
            log(f"  project {project_id}: {status}")
            if status == "ready":
                return state
            if status == "failed":
                raise ElevenLabsError(f"project failed: {state.get('error')}")
            if time.time() > deadline:
                raise ElevenLabsError(f"timed out waiting for project {project_id}")
            sleep(interval)

    def wait_for_targets(
        self, project_id: str, *, timeout: float = 1800, interval: float = 5,
        sleep=time.sleep, log=print,
    ) -> list[dict]:
        deadline = time.time() + timeout
        while True:
            rows = self.targets(project_id)
            log("  " + " ".join(
                f"{row['target_language']}={row['status']}" for row in rows
            ) or "  (no targets yet)")
            if rows and all(
                row["status"] not in ("queued", "processing") for row in rows
            ):
                return rows
            if time.time() > deadline:
                raise ElevenLabsError("timed out waiting for language targets")
            sleep(interval)

    # ---------------------------------------------------- speech to text ----
    def transcribe_words(self, path: Path | str) -> tuple[list[dict], str]:
        """Return (word timings, full text) for a media file."""
        body, content_type = encode_multipart(
            {"model_id": STT_MODEL, "timestamps_granularity": "word"},
            [("file", Path(path))],
        )
        payload = self._call("POST", "/speech-to-text", body, content_type)
        words = [w for w in payload.get("words", []) if w.get("type") == "word"]
        return words, payload.get("text", "")

    # ------------------------------------------------------------- files ----
    def download(self, url: str, dest: Path | str) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=self.timeout) as response, \
                open(dest, "wb") as handle:
            while chunk := response.read(1 << 20):
                handle.write(chunk)
        return dest
