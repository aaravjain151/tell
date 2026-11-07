"""DoubleSpeak - Streamlit demo UI.

Large fonts, high contrast, plain language - built for older users. You can
upload a clip or record one, then the on-device pipeline tells you whether the
call may be a scam. A network-proof panel is always visible so you can see your
call never leaves the computer.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import os
import tempfile

import streamlit as st

# Importing the package applies the offline guard before any ML library loads.
from doublespeak import config, net_monitor, secure_store
from doublespeak.detector import (
    LEVEL_HIGH,
    LEVEL_LOW,
    LEVEL_MEDIUM,
    get_pipeline,
    load_audio,
)

# Optional brand logo. If assets/logo.png exists it is used for the browser-tab
# icon and the in-app header; otherwise we fall back to the shield emoji so the
# app still runs with no image present.
_LOGO_PATH = config.PROJECT_ROOT / "assets" / "logo.png"
_LOGO = str(_LOGO_PATH) if _LOGO_PATH.exists() else None

st.set_page_config(
    page_title="DoubleSpeak",
    page_icon=_LOGO or "🛡️",
    layout="centered",
)

# --------------------------------------------------------------------------- #
# Large-font / high-contrast styling
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
      html, body, [class*="css"] { font-size: 21px; }
      h1 { font-size: 48px !important; }
      h2 { font-size: 34px !important; }
      .alert {
          padding: 32px; border-radius: 18px; text-align: center;
          font-size: 40px; font-weight: 800; margin: 16px 0; line-height: 1.2;
      }
      .alert .sub { font-size: 24px; font-weight: 500; display:block; margin-top:8px; }
      .high   { background:#fce8e6; color:#a50e0e; border:4px solid #a50e0e; }
      .medium { background:#fef7e0; color:#8a6d00; border:4px solid #b06000; }
      .low    { background:#e6f4ea; color:#137333; border:4px solid #137333; }
      .net-ok  { background:#e6f4ea; color:#137333; border:3px solid #137333;
                 border-radius:14px; padding:18px; text-align:center;
                 font-size:28px; font-weight:800; }
      .net-bad { background:#fce8e6; color:#a50e0e; border:3px solid #a50e0e;
                 border-radius:14px; padding:18px; text-align:center;
                 font-size:28px; font-weight:800; }
      .stButton>button { font-size: 24px; padding: 14px 22px; border-radius: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

_ALERT_CLASS = {LEVEL_HIGH: "high", LEVEL_MEDIUM: "medium", LEVEL_LOW: "low"}
_ALERT_TEXT = {
    LEVEL_HIGH: "This may be a scam",
    LEVEL_MEDIUM: "Be careful with this call",
    LEVEL_LOW: "This call looks okay",
}
_ALERT_SUB = {
    LEVEL_HIGH: "Do not send money or share codes. Hang up and call back.",
    LEVEL_MEDIUM: "Some of what was said sounds risky. Take your time.",
    LEVEL_LOW: "We did not spot scam tactics or a fake voice.",
}


@st.cache_resource(show_spinner="Getting the detector ready (runs on this "
                                "computer only)...")
def _pipeline():
    return get_pipeline()


def _render_result(result) -> None:  # noqa: ANN001
    css = _ALERT_CLASS[result.level]
    st.markdown(
        f'<div class="alert {css}">{_ALERT_TEXT[result.level]}'
        f'<span class="sub">{_ALERT_SUB[result.level]}</span></div>',
        unsafe_allow_html=True,
    )

    st.subheader("Why we think so")
    for reason in result.reasons:
        st.markdown(f"- {reason}")

    # Call-a-real-contact buttons (display-only for the demo).
    st.subheader("Not sure? Call someone you trust on their real number")
    cols = st.columns(len(config.CONTACTS))
    for col, contact in zip(cols, config.CONTACTS):
        with col:
            if st.button(f"Call {contact.name}", key=f"call-{contact.name}"):
                st.info(f"{contact.name}: **{contact.phone}**")
            st.caption(contact.phone)

    # Per-window voice-score chart.
    if result.per_window_voice:
        st.subheader("Fake-voice score over the call")
        st.caption("Higher means the voice is more likely an AI copy.")
        st.line_chart({"fake voice score": result.per_window_voice})

    with st.expander("Words we heard (kept in memory only, never saved)"):
        st.write(result.transcript or "(no clear speech)")

    # Save to encrypted history for High/Medium (never audio or transcript).
    if result.level in (LEVEL_HIGH, LEVEL_MEDIUM):
        secure_store.save_alert(result.level, result.reasons)


def _run_on_tempfile(uploaded) -> None:  # noqa: ANN001
    """Decode an uploaded/recorded clip in memory, run the pipeline, show it."""
    suffix = os.path.splitext(getattr(uploaded, "name", "clip.wav"))[1] or ".wav"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(uploaded.getbuffer() if hasattr(uploaded, "getbuffer")
                  else uploaded.read())
        tmp.flush()
        tmp.close()
        audio = load_audio(tmp.name)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    with st.spinner("Checking the call..."):
        result = _pipeline().run(audio)
    _render_result(result)


def _run_on_path(path: str) -> None:
    """Load a clip from a local path in memory and run the pipeline."""
    audio = load_audio(path)
    with st.spinner("Checking the call..."):
        result = _pipeline().run(audio)
    _render_result(result)


#: Where the bundled sample datasets live (pulled from the voice-clips branch).
_SAMPLES_DIR = config.PROJECT_ROOT / "data" / "calls"


@st.cache_data(show_spinner=False)
def _discover_samples() -> dict[str, list[tuple[str, str]]]:
    """Group sample clips by dataset folder.

    Returns {dataset_label: [(display_name, full_path), ...]}. Only primary
    .wav files are listed (the 8 kHz 'opus8k' duplicates are hidden to keep the
    menu short). Nothing is loaded here - just the file listing.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    if not _SAMPLES_DIR.exists():
        return out
    for wav in sorted(_SAMPLES_DIR.rglob("*.wav")):
        if ".opus8k" in wav.name:
            continue
        # Label by the dataset folder (e.g. "human/sanath", "gradium").
        rel = wav.relative_to(_SAMPLES_DIR)
        dataset = str(rel.parent).replace("\\", "/")
        out.setdefault(dataset, []).append((wav.stem, str(wav)))
    return out


def main() -> None:
    if _LOGO is not None:
        logo_col, title_col = st.columns([1, 5], vertical_alignment="center")
        with logo_col:
            st.image(_LOGO, width=96)
        with title_col:
            st.title("DoubleSpeak")
    else:
        st.title("🛡️ DoubleSpeak")
    st.write("A friendly helper that spots fake voices and scam calls.")

    # Always-visible network proof.
    net_monitor.render_panel(st)

    st.divider()
    st.header("Check a call")
    samples = _discover_samples()
    tab_labels = ["Record now", "Upload a file"]
    if samples:
        tab_labels.append("Sample clips")
    tabs = st.tabs(tab_labels)
    record_tab, upload_tab = tabs[0], tabs[1]
    sample_tab = tabs[2] if samples else None

    with record_tab:
        # st.audio_input was added in Streamlit 1.40. Degrade gracefully on
        # older versions instead of crashing the whole app.
        if hasattr(st, "audio_input"):
            st.write("Press the microphone, speak or hold it to your phone, "
                     "then stop.")
            recorded = st.audio_input("Record the call")
            if recorded is not None and st.button(
                "Check this recording", type="primary", key="check-rec"
            ):
                _run_on_tempfile(recorded)
        else:
            st.warning(
                "In-app recording needs Streamlit 1.40 or newer. "
                "You can still check a call using the **Upload a file** tab."
            )

    with upload_tab:
        st.write("Choose a saved recording. It is read into memory, not copied.")
        uploaded = st.file_uploader(
            "Audio file", type=["wav", "mp3", "m4a", "flac", "ogg"]
        )
        if uploaded is not None and st.button("Check this file", type="primary",
                                              key="check-up"):
            _run_on_tempfile(uploaded)

    if sample_tab is not None:
        with sample_tab:
            st.write("Try one of the bundled example calls. These run through "
                     "the exact same on-device pipeline.")
            dataset = st.selectbox(
                "Dataset", sorted(samples.keys()),
                help="human/* are real recordings; gradium/qwen3tts are "
                     "AI-generated voices.",
            )
            clips = samples[dataset]
            choice = st.selectbox(
                "Clip", [name for name, _ in clips], key="sample-clip",
            )
            path = dict(clips)[choice]
            if st.button("Check this sample", type="primary", key="check-sample"):
                _run_on_path(path)

    st.divider()
    with st.expander("Past warnings (saved encrypted on this computer)"):
        alerts = secure_store.load_alerts()
        if not alerts:
            st.info("No warnings saved yet.")
        else:
            for a in alerts:
                st.markdown(f"**{a.timestamp}** - {a.level}")
                for r in a.reasons:
                    st.markdown(f"  - {r}")
            if st.button("Delete all saved warnings"):
                secure_store.wipe_all()
                st.rerun()


if __name__ == "__main__":
    main()
