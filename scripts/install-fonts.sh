#!/usr/bin/env bash
# Install the fonts libass needs for CJK and Arabic subtitles, without root.
set -euo pipefail
cd "$(dirname "$0")/.."
exec "${PYTHON:-python3}" -m dubstitch fonts
