"""Command line interface: ``python3 -m dubstitch <command>``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config, fonts, media, pipeline
from .elevenlabs_api import Client, ElevenLabsError

DEFAULT_WORKDIR = "work"
DEFAULT_TARGETS = ",".join(lang for lang in config.LANGS if lang != config.ORIGINAL)


def split_langs(value: str) -> list[str]:
    langs = [part.strip() for part in value.split(",") if part.strip()]
    unknown = [lang for lang in langs if lang not in config.LANG_NAME]
    if unknown:
        raise SystemExit(f"unknown language code(s): {', '.join(unknown)}")
    return langs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dubstitch",
        description="Dub a short clip into several languages with ElevenLabs, "
                    "subtitle each version, and stitch them into one video.",
    )
    parser.add_argument("--workdir", default=DEFAULT_WORKDIR,
                        help=f"scratch directory (default: ./{DEFAULT_WORKDIR})")
    parser.add_argument("--state", default=None,
                        help="state file (default: <workdir>/state.json)")
    parser.add_argument("--api-key", default=None,
                        help="override the ELEVENLABS_API_KEY environment variable")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("fonts", help="download the CJK/Arabic fonts libass needs")

    clip = sub.add_parser("clip", help="download just the wanted slice of a video")
    clip.add_argument("url")
    clip.add_argument("--start", type=float, default=0.0)
    clip.add_argument("--duration", type=float, default=5.0)
    clip.add_argument("--out", default=None)

    submit = sub.add_parser(
        "submit", help="create the ElevenLabs project and queue the targets (bills)"
    )
    source = submit.add_mutually_exclusive_group()
    source.add_argument("--source", default=None, help="local media file to dub")
    source.add_argument("--source-url", default=None,
                        help="public URL ElevenLabs fetches server-side")
    submit.add_argument("--source-lang", default=config.ORIGINAL)
    submit.add_argument("--targets", default=DEFAULT_TARGETS)
    submit.add_argument("--name", default=None, help="label stored on the project")

    sub.add_parser("fetch", help="wait for the dubs and download the audio")

    render = sub.add_parser("render", help="subtitle, burn in, and stitch")
    render.add_argument("--layout", choices=("band", "overlay"), default="band")
    render.add_argument("--order", default=None,
                        help="comma separated segment order, e.g. es,en,de,ja")

    run = sub.add_parser("all", help="clip, submit, fetch and render in one go")
    run.add_argument("url")
    run.add_argument("--duration", type=float, default=5.0)
    run.add_argument("--start", type=float, default=0.0)
    run.add_argument("--source-lang", default=config.ORIGINAL)
    run.add_argument("--targets", default=DEFAULT_TARGETS)
    run.add_argument("--name", default=None)
    run.add_argument("--layout", choices=("band", "overlay"), default="band")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workdir = Path(args.workdir)
    state_path = Path(args.state) if args.state else workdir / "state.json"
    state = pipeline.State.load(state_path)

    try:
        if args.command == "fonts":
            installed = fonts.ensure()
            print("installed: " + (", ".join(installed) if installed else "nothing to do"))
            return 0

        if args.command == "clip":
            dest = Path(args.out) if args.out else \
                workdir / "source" / f"clip{int(args.duration)}s.mp4"
            print("downloading clip")
            pipeline.download_clip(args.url, dest, start=args.start,
                                   seconds=args.duration)
            state.source_clip = str(dest.resolve())
            state.source_url = args.url
            state.save(state_path)
            return 0

        if args.command == "submit":
            client = Client(args.api_key, workdir)
            source = args.source or state.source_clip
            if not source and not args.source_url:
                raise SystemExit("pass --source, --source-url, or run `clip` first")
            print("submitting to ElevenLabs")
            pipeline.submit(client, state, source=source,
                            source_url=args.source_url,
                            source_language=args.source_lang,
                            targets=split_langs(args.targets), name=args.name)
            state.order = [state.source_language] + [
                lang for lang in split_langs(args.targets)
                if lang != state.source_language
            ]
            state.save(state_path)
            print(f"state -> {state_path}")
            return 0

        if args.command == "fetch":
            client = Client(args.api_key, workdir)
            print(f"fetching project {state.project_id}")
            pipeline.fetch(client, state, workdir)
            state.save(state_path)
            return 0

        if args.command == "render":
            order = split_langs(args.order) if args.order else None
            out = pipeline.render(state, workdir, layout=args.layout, order=order)
            print(f"rendered -> {out}")
            return 0

        if args.command == "all":
            targets = split_langs(args.targets)
            dest = workdir / "source" / f"clip{int(args.duration)}s.mp4"
            print("downloading clip")
            pipeline.download_clip(args.url, dest, start=args.start,
                                   seconds=args.duration)
            state.source_clip = str(dest.resolve())
            state.source_url = args.url
            state.source_language = args.source_lang
            state.order = [args.source_lang] + [
                lang for lang in targets if lang != args.source_lang
            ]
            client = Client(args.api_key, workdir)
            print("submitting to ElevenLabs")
            pipeline.submit(client, state, source=dest,
                            source_language=args.source_lang,
                            targets=targets, name=args.name)
            state.save(state_path)
            print("fetching dubs")
            pipeline.fetch(client, state, workdir)
            print("rendering")
            out = pipeline.render(state, workdir, layout=args.layout, client=client)
            print(f"rendered -> {out}")
            return 0

    except (ElevenLabsError, media.MediaError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
