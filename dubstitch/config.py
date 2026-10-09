"""Static configuration: layout, subtitle styling and per-language data.

Everything a user might reasonably want to tweak lives here, so the rest of the
package stays declarative.
"""

from __future__ import annotations

# --------------------------------------------------------------- layout ----
VIDEO_W = 1280
VIDEO_H = 720
BAND_H = 92                    # solid title band stacked above the clip
TOTAL_H = VIDEO_H + BAND_H

# -------------------------------------------------------------- styling ----
SUB_SIZE = 48                  # subtitle font size on the ASS canvas
SUB_BORDER = 6                 # black outline thickness
HEADER_SIZE = 52               # language label in the title band
SUB_COLOUR = "&H0000FFFF"      # ASS colours are &HAABBGGRR -> opaque yellow
SUB_OUTLINE = "&H00000000"     # opaque black
SUB_MARGIN = 34                # distance from the bottom of the canvas
HEADER_MARGIN = 15             # distance from the top of the canvas

# ------------------------------------------------------------ languages ----
ORIGINAL = "es"                # the untouched source recording, not a dub
LANGS = ("es", "en", "de", "ja", "fr", "ar", "ko", "it")

LANG_NAME = {
    "es": "SPANISH", "en": "ENGLISH", "de": "GERMAN", "ja": "JAPANESE",
    "fr": "FRENCH", "ar": "ARABIC", "ko": "KOREAN", "it": "ITALIAN",
}
LANG_NATIVE = {
    "es": "ESPAÑOL", "en": "", "de": "DEUTSCH", "ja": "日本語",
    "fr": "FRANÇAIS", "ar": "العربية", "ko": "한국어", "it": "ITALIANO",
}
# Font family per language. The Latin families ship with every distro; the CJK
# and Arabic ones are fetched on demand by dubstitch.fonts.
FONT = {
    "es": "Liberation Sans", "en": "Liberation Sans", "de": "Liberation Sans",
    "fr": "Liberation Sans", "it": "Liberation Sans",
    "ja": "Noto Sans JP", "ko": "Noto Sans KR", "ar": "Noto Sans Arabic",
}
# family -> (local filename, download URL) for the fonts libass needs
REQUIRED_FONTS = {
    "Noto Sans JP": (
        "NotoSansJP-var.ttf",
        "https://github.com/google/fonts/raw/main/ofl/notosansjp/"
        "NotoSansJP%5Bwght%5D.ttf",
    ),
    "Noto Sans KR": (
        "NotoSansKR-var.ttf",
        "https://github.com/google/fonts/raw/main/ofl/notosanskr/"
        "NotoSansKR%5Bwght%5D.ttf",
    ),
    "Noto Sans Arabic": (
        "NotoSansArabic-var.ttf",
        "https://github.com/google/fonts/raw/main/ofl/notosansarabic/"
        "NotoSansArabic%5Bwdth,wght%5D.ttf",
    ),
}

RTL = frozenset({"ar", "he", "fa", "ur"})
SPACELESS = frozenset({"ja", "zh", "yue", "cmn"})   # scribe tokenises per character

# Scribe hears this piece of slang differently on every run ("mangüango",
# "mangoangua", ...), so the original line is pinned to what is actually said.
MANUAL_CUE = {"es": "Coño, pero qué manguangua. ¿Ah?"}

# ------------------------------------------------------------- API models ----
MODEL_ID = "dubbing_v2"
STT_MODEL = "scribe_v1"

# ------------------------------------------------------------ cue shaping ----
CUE_GAP = 0.30                 # seconds of silence that force a new cue
CUE_MAX_CHARS = 30             # characters per rendered line
CUE_MAX_LINES = 2              # lines per cue
CUE_MIN_DURATION = 0.90        # keep one-word cues on screen long enough
CUE_LEAD = 0.06                # show slightly before the word starts
CUE_TAIL = 0.35                # linger slightly after the word ends
