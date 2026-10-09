"""Offline tests: cue shaping, ASS generation, multipart encoding, state.

Nothing here touches the network or the ElevenLabs API. `submit` costs money, so
it is deliberately not exercised by the test suite.
"""

from __future__ import annotations

from dubstitch import config, fonts, subtitles
from dubstitch.elevenlabs_api import encode_multipart
from dubstitch.pipeline import State


def word(text: str, start: float, end: float) -> dict:
    return {"text": text, "start": start, "end": end, "type": "word"}


def dialogue_lines(document: str) -> list[str]:
    return [line for line in document.splitlines() if line.startswith("Dialogue:")]


# ------------------------------------------------------------- timestamps ----
def test_timestamp_formats_centiseconds():
    assert subtitles.timestamp(0) == "0:00:00.00"
    assert subtitles.timestamp(5.013) == "0:00:05.01"
    assert subtitles.timestamp(61.5) == "0:01:01.50"


def test_timestamp_clamps_negatives():
    assert subtitles.timestamp(-3) == "0:00:00.00"


# ------------------------------------------------------------ cue shaping ----
def test_cues_split_on_pauses():
    words = [word("Hey,", 1.76, 1.86), word("what", 1.92, 2.04),
             word("a", 2.08, 2.18), word("freeloader,", 2.24, 2.82),
             word("man.", 2.90, 3.26), word("Huh?", 3.62, 3.76)]
    assert [cue[2] for cue in subtitles.build_cues(words, "en")] == [
        "Hey, what a freeloader, man.", "Huh?"
    ]


def test_short_pauses_do_not_split():
    words = [word("a", 0.0, 0.4), word("b", 0.5, 0.9)]
    assert len(subtitles.build_cues(words, "en")) == 1


def test_japanese_tokens_join_without_spaces():
    words = [word(ch, i * 0.1, i * 0.1 + 0.08) for i, ch in enumerate("おい、何")]
    assert subtitles.build_cues(words, "ja")[0][2] == "おい、何"


def test_per_character_tokens_are_not_split_mid_word():
    text = "おい、何なんだよ、このぐうたら野郎は。あ？"
    words = [word(ch, i * 0.1, i * 0.1 + 0.08) for i, ch in enumerate(text)]
    cues = subtitles.build_cues(words, "ja")
    assert len(cues) == 1
    assert cues[0][2] == text


def test_long_text_wraps_to_at_most_two_lines():
    words = [word(w, i * 0.2, i * 0.2 + 0.15) for i, w in
             enumerate("Sag mal, was soll der Blödsinn, Mann? Hä?".split())]
    cues = subtitles.build_cues(words, "de")
    assert len(cues) == 1
    assert cues[0][2].count(r"\N") == 1


def test_character_budget_starts_a_new_cue():
    # 40 + 40 characters against a 2 x 30 character budget
    words = [word("x" * 40, 0.0, 0.5), word("y" * 40, 0.6, 1.0)]
    assert len(subtitles.build_cues(words, "en")) == 2


def test_manual_cue_overrides_transcription_of_the_original():
    words = [word("mangoangua", 1.0, 2.0)]
    assert subtitles.build_cues(words, "es")[0][2] == config.MANUAL_CUE["es"]


def test_no_words_means_no_cues():
    assert subtitles.build_cues([], "en") == []


# --------------------------------------------------------- ASS generation ----
def test_band_layout_geometry_and_colour():
    document = subtitles.ass_document("en", [], 5.0, "band")
    assert f"PlayResY: {config.TOTAL_H}" in document
    assert config.SUB_COLOUR in document      # yellow text
    assert config.SUB_OUTLINE in document     # black border
    assert "ENGLISH" in document


def test_overlay_layout_keeps_native_frame_height():
    document = subtitles.ass_document("en", [], 5.0, "overlay")
    assert f"PlayResY: {config.VIDEO_H}" in document


def test_rtl_languages_get_the_line_break_override():
    document = subtitles.ass_document("ar", [(0.0, 1.0, "مرحبا")], 5.0, "band")
    assert r"\q2مرحبا" in document


def test_short_cues_hold_a_minimum_screen_time():
    cues = subtitles.build_cues([word("Ah", 4.88, 4.88)], "fr")
    line = dialogue_lines(subtitles.ass_document("fr", cues, 5.013, "band"))[1]
    start, end = line.split(",")[1], line.split(",")[2]
    assert end > start
    assert end <= subtitles.timestamp(5.013)


def test_title_band_includes_the_native_name():
    assert subtitles.label("ja") == "JAPANESE  ·  日本語"
    assert subtitles.label("en") == "ENGLISH"


def test_header_line_spans_the_whole_segment():
    line = dialogue_lines(subtitles.ass_document("en", [], 5.0, "band"))[0]
    assert line.split(",")[1] == subtitles.timestamp(0)
    assert line.split(",")[2] == subtitles.timestamp(5.0)


# --------------------------------------------------------- infrastructure ----
def test_multipart_encoder_sets_a_boundary():
    body, content_type = encode_multipart({"target_language": "en"}, [])
    assert content_type.startswith("multipart/form-data; boundary=")
    boundary = content_type.split("boundary=", 1)[1]
    assert b'name="target_language"' in body
    assert b"en" in body
    assert body.rstrip().endswith(f"--{boundary}--".encode())


def test_default_language_order_starts_with_the_original():
    assert config.LANGS[0] == config.ORIGINAL
    assert config.ORIGINAL not in [lang for lang in config.LANGS[1:] if lang == "es"]


def test_state_round_trips(tmp_path):
    state = State(project_id="proj_x", targets={"en": "lang_y"}, order=["es", "en"])
    restored = State.load(state.save(tmp_path / "state.json"))
    assert (restored.project_id, restored.targets, restored.order) == \
        ("proj_x", {"en": "lang_y"}, ["es", "en"])


def test_state_ignores_unknown_keys_and_missing_files(tmp_path):
    assert State.load(tmp_path / "absent.json").project_id is None
    path = tmp_path / "state.json"
    path.write_text('{"project_id": "proj_p", "leftover": 1}', encoding="utf-8")
    assert State.load(path).project_id == "proj_p"


def test_missing_fonts_reports_unknown_families():
    required = {"Not A Real Font Family 12345":
                ("x.ttf", "https://example.invalid/x.ttf")}
    assert fonts.missing(required) == ["Not A Real Font Family 12345"]
