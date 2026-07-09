"""Voice pipeline — paper §9.

Voice is a perception/output modality on the SAME event bus, not a subsystem:

    mic → STT (Whisper local / hosted) → event bus → Sarva → text → TTS → audio

This is a SCAFFOLD. STT/TTS backends are optional deps and degrade gracefully
(like the Harness browser tools) when not installed, so importing this module
never requires audio libraries. The genuinely-working, testable pieces are:

  * `transcription_to_event()` — shapes an STT result into the same event dict a
    text turn produces, so the one loop handles both modalities.
  * the human-in-the-loop **correction store** (§9.1): each (wrong, right) pair a
    user fixes is persisted as a per-user training signal; after enough
    corrections, per-user STT fine-tuning reduces error rate.
  * one unconditional safety rule: high-risk actions need visual confirmation
    regardless of input modality (a misheard command cannot itself act).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_CORR_PATH = Path(
    os.environ.get(
        "SARVA_VOICE_CORRECTIONS",
        str(Path(__file__).resolve().parents[2] / "sarva_training" / "data" / "voice" / "corrections.jsonl"),
    )
)


def stt_available() -> str | None:
    for mod, name in (("faster_whisper", "faster-whisper"), ("whisper", "openai-whisper")):
        try:
            __import__(mod)
            return name
        except Exception:
            continue
    return None


def tts_available() -> str | None:
    for mod, name in (("TTS", "coqui-tts"), ("pyttsx3", "pyttsx3")):
        try:
            __import__(mod)
            return name
        except Exception:
            continue
    return None


@dataclass
class Transcription:
    text: str
    words: list[dict] = field(default_factory=list)  # [{word, confidence}]
    low_confidence: list[str] = field(default_factory=list)
    engine: str = "none"

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "words": self.words,
            "low_confidence": self.low_confidence,
            "engine": self.engine,
        }


def transcribe(audio_path: str, *, model: str = "large-v3", low_conf: float = 0.6) -> dict:
    """STT → Transcription. Degrades cleanly if no engine installed."""
    engine = stt_available()
    if not engine:
        return {
            "ok": False,
            "error": "No STT backend. Install faster-whisper (pip install faster-whisper).",
        }
    if not os.path.exists(audio_path):
        return {"ok": False, "error": f"audio not found: {audio_path}"}
    try:
        from faster_whisper import WhisperModel  # type: ignore

        m = WhisperModel(model, device="auto", compute_type="int8")
        segments, _ = m.transcribe(audio_path, word_timestamps=True)
        words: list[dict] = []
        for seg in segments:
            for w in getattr(seg, "words", []) or []:
                words.append({"word": w.word, "confidence": float(getattr(w, "probability", 1.0))})
        text = "".join(w["word"] for w in words) or ""
        low = [w["word"].strip() for w in words if w["confidence"] < low_conf]
        return {"ok": True, **Transcription(text=text.strip(), words=words, low_confidence=low, engine=engine).to_dict()}
    except Exception as exc:  # pragma: no cover - backend-specific
        return {"ok": False, "error": f"stt_failed: {exc}"}


def transcription_to_event(transcription: dict, *, user_id: str | None = None) -> dict:
    """Shape an STT result into the same event a text turn feeds to the loop."""
    return {
        "modality": "voice",
        "type": "text",  # after STT it is just text on the bus
        "content": transcription.get("text", ""),
        "user_id": user_id,
        "meta": {
            "engine": transcription.get("engine"),
            "low_confidence": transcription.get("low_confidence", []),
        },
    }


def record_correction(wrong: str, right: str, *, user_id: str | None = None) -> bool:
    """Persist a (wrong, right) STT correction as a per-user training signal (§9.1)."""
    if not wrong or not right or wrong == right:
        return False
    try:
        _CORR_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _CORR_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id, "wrong": wrong, "right": right,
            }, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def correction_count(user_id: str | None = None) -> int:
    if not _CORR_PATH.exists():
        return 0
    n = 0
    for ln in _CORR_PATH.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if user_id is None or row.get("user_id") == user_id:
            n += 1
    return n


# §9 unconditional rule: voice cannot itself trigger a high-risk action.
HIGH_RISK = {"shell", "run_terminal", "open_app", "browser_execute", "git_commit", "delete"}


def requires_visual_confirmation(tool: str, modality: str) -> bool:
    """High-risk actions always need visual confirmation, regardless of modality."""
    return tool in HIGH_RISK


def speak(text: str) -> dict:
    """TTS → audio. Degrades cleanly if no engine installed."""
    engine = tts_available()
    if not engine:
        return {"ok": False, "error": "No TTS backend. Install pyttsx3 (pip install pyttsx3)."}
    try:
        if engine == "pyttsx3":
            import pyttsx3  # type: ignore

            e = pyttsx3.init()
            e.say(text)
            e.runAndWait()
        return {"ok": True, "engine": engine, "chars": len(text)}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"tts_failed: {exc}"}
