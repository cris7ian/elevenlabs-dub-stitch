"""Make sure the fonts libass needs are present for the current user.

System font packages need root, so anything missing is fetched into the user's
font directory instead and picked up by fontconfig.
"""

from __future__ import annotations

import shutil
import subprocess
import urllib.request
from pathlib import Path

from . import config

FONT_DIR = Path.home() / ".local" / "share" / "fonts" / "noto-dub"


def installed_families() -> set[str]:
    """Every font family fontconfig knows about.

    ``fc-list``'s default format is ``<file>: <family>``, so ask for the primary
    family of each face explicitly — otherwise the file path leaks into the name
    and nothing ever matches.
    """
    if not shutil.which("fc-list"):
        return set()
    proc = subprocess.run(
        ["fc-list", "--format", "%{family[0]}\n"], capture_output=True, text=True
    )
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def missing(required: dict[str, tuple[str, str]] | None = None) -> list[str]:
    required = config.REQUIRED_FONTS if required is None else required
    have = installed_families()
    return [family for family in required if family not in have]


def ensure(
    required: dict[str, tuple[str, str]] | None = None,
    *,
    log=print,
) -> list[str]:
    """Download whichever required fonts are missing.

    Returns the families that were installed (empty when nothing was needed).
    """
    required = config.REQUIRED_FONTS if required is None else required
    have = installed_families()
    FONT_DIR.mkdir(parents=True, exist_ok=True)

    installed: list[str] = []
    for family, (filename, url) in required.items():
        if family in have:
            continue
        dest = FONT_DIR / filename
        if not dest.exists():
            log(f"  downloading {family} -> {dest}")
            urllib.request.urlretrieve(url, dest)      # noqa: S310 - fixed hosts
        installed.append(family)

    if installed and shutil.which("fc-cache"):
        subprocess.run(["fc-cache", "-f", str(FONT_DIR)], check=False,
                       capture_output=True)
        log(f"  refreshed fontconfig cache for {FONT_DIR}")
    return installed
