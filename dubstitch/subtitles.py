"""Subtitle timing and ASS generation.

Pure functions: give them word timings, get back an .ass document. All file and
network I/O lives in the pipeline.
"""

from __future__ import annotations

from pathlib import Path

from . import config


def timestamp(seconds: float) -> str:
    """Format an ASS timestamp: ``H:MM:SS.cc``."""
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int(seconds % 3600 // 60)
    rest = seconds % 60
    return f"{hours}:{minutes:02d}:{rest:05.2f}"


def separator(lang: str) -> str:
    """Japanese and friends are tokenised per character, so they join tight."""
    return "" if lang in config.SPACELESS else " "


def group_words(
    words: list[dict],
    lang: str,
    *,
    gap: float | None = None,
    max_chars: int | None = None,
    max_lines: int | None = None,
) -> list[list[dict]]:
    """Split word timings into cue-sized groups.

    A new group starts on a pause longer than ``gap``, or when the running text
    would exceed ``max_chars * max_lines`` characters. The budget is measured in
    characters, not tokens, so per-character languages are not split mid-word.
    """
    gap = config.CUE_GAP if gap is None else gap
    max_chars = config.CUE_MAX_CHARS if max_chars is None else max_chars
    max_lines = config.CUE_MAX_LINES if max_lines is None else max_lines
    sep = separator(lang)
    budget = max_chars * max_lines

    groups: list[list[dict]] = []
    current: list[dict] = []
    used = 0
    for word in words:
        text = word.get("text") or ""
        if not text:
            continue
        if current and (
            word["start"] - current[-1]["end"] >= gap or used + len(text) > budget
        ):
            groups.append(current)
            current, used = [], 0
        current.append(word)
        used += len(text) + len(sep)
    if current:
        groups.append(current)
    return groups


def wrap(
    words: list[dict],
    lang: str,
    *,
    max_chars: int | None = None,
    max_lines: int | None = None,
) -> str:
    """Join a group into at most ``max_lines`` lines of about ``max_chars``."""
    max_chars = config.CUE_MAX_CHARS if max_chars is None else max_chars
    max_lines = config.CUE_MAX_LINES if max_lines is None else max_lines
    sep = separator(lang)

    lines: list[str] = []
    line = ""
    for word in words:
        candidate = (line + sep + word["text"]).strip()
        if line and len(candidate) > max_chars and len(lines) < max_lines - 1:
            lines.append(line)
            line = word["text"]
        else:
            line = candidate
    if line:
        lines.append(line)
    return r"\N".join(lines)


def build_cues(
    words: list[dict],
    lang: str,
    *,
    manual: dict[str, str] | None = None,
    **kwargs,
) -> list[tuple[float, float, str]]:
    """Return ``(start, end, text)`` cues for one language."""
    if not words:
        return []
    manual = config.MANUAL_CUE if manual is None else manual
    if lang in manual:
        return [(words[0]["start"], words[-1]["end"], manual[lang])]
    return [
        (group[0]["start"], group[-1]["end"], wrap(group, lang, **kwargs))
        for group in group_words(words, lang, **kwargs)
    ]


def style_lines(lang: str, layout: str) -> tuple[str, str, int]:
    """Return the (Header, Sub, PlayResY) style rows for a layout."""
    font = config.FONT.get(lang, "Liberation Sans")
    if layout == "band":
        header = (
            f"Header,{font},{config.HEADER_SIZE},&H00FFFFFF,&H00FFFFFF,"
            f"&H00000000,&H00000000,-1,0,0,0,100,100,1,0,1,0,0,8,40,40,"
            f"{config.HEADER_MARGIN},1"
        )
        sub_margin = config.SUB_MARGIN
        play_res_y = config.TOTAL_H
    else:
        header = (
            f"Header,{font},{config.HEADER_SIZE - 4},&H00FFFFFF,&H00FFFFFF,"
            f"&H99101010,&H99101010,-1,0,0,0,100,100,1,0,3,14,0,8,40,40,20,1"
        )
        sub_margin = 36
        play_res_y = config.VIDEO_H
    sub = (
        f"Sub,{font},{config.SUB_SIZE},{config.SUB_COLOUR},{config.SUB_COLOUR},"
        f"{config.SUB_OUTLINE},&H80000000,-1,0,0,0,100,100,0,0,1,"
        f"{config.SUB_BORDER},1,2,60,60,{sub_margin},1"
    )
    return header, sub, play_res_y


def label(lang: str) -> str:
    """The text shown in the title band, e.g. ``JAPANESE  ·  日本語``."""
    name = config.LANG_NAME.get(lang, lang.upper())
    native = config.LANG_NATIVE.get(lang, "")
    return f"{name}  ·  {native}" if native else name


def ass_document(
    lang: str, cues: list[tuple[float, float, str]], duration: float,
    layout: str = "band",
) -> str:
    """Render the full .ass document for one segment."""
    header, sub, play_res_y = style_lines(lang, layout)
    rtl = "\\q2" if lang in config.RTL else ""

    rows = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {config.VIDEO_W}",
        f"PlayResY: {play_res_y}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        f"Style: {header}",
        f"Style: {sub}",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text",
        f"Dialogue: 0,{timestamp(0)},{timestamp(duration)},Header,,0,0,0,,"
        f"{{\\fad(200,200)}}{label(lang)}",
    ]
    for start, end, text in cues:
        shown_from = max(0.0, start - config.CUE_LEAD)
        shown_to = min(
            duration, max(end + config.CUE_TAIL, shown_from + config.CUE_MIN_DURATION)
        )
        rows.append(
            f"Dialogue: 0,{timestamp(shown_from)},{timestamp(shown_to)},Sub,,0,0,0,,"
            f"{rtl}{text}"
        )
    return "\n".join(rows) + "\n"


def write_ass(path: Path | str, document: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
    return path
