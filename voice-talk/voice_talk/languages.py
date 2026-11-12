"""Languages supported by Qwen3-TTS (and the matching Whisper / prompt names)."""
from __future__ import annotations

# code -> (name used in prompts and as the Qwen3-TTS `language`, whisper code, disclosure line)
LANGUAGES: dict[str, dict[str, str]] = {
    "en": {"name": "English", "whisper": "en", "disclosure": "This voice is AI-generated."},
    "es": {"name": "Spanish", "whisper": "es", "disclosure": "Esta voz está generada por IA."},
    "fr": {"name": "French", "whisper": "fr", "disclosure": "Cette voix est générée par IA."},
    "de": {"name": "German", "whisper": "de", "disclosure": "Diese Stimme wurde von KI erzeugt."},
    "it": {"name": "Italian", "whisper": "it", "disclosure": "Questa voce è generata dall'IA."},
    "pt": {"name": "Portuguese", "whisper": "pt", "disclosure": "Esta voz é gerada por IA."},
    "ja": {"name": "Japanese", "whisper": "ja", "disclosure": "この音声はAIによって生成されています。"},
    "ko": {"name": "Korean", "whisper": "ko", "disclosure": "이 목소리는 AI로 생성되었습니다."},
    "zh": {"name": "Chinese", "whisper": "zh", "disclosure": "这个声音是由人工智能生成的。"},
    "ru": {"name": "Russian", "whisper": "ru", "disclosure": "Этот голос сгенерирован ИИ."},
}


def lang_name(code: str) -> str:
    try:
        return LANGUAGES[code]["name"]
    except KeyError:
        raise ValueError(f"unsupported language: {code!r}") from None


def disclosure_line(code: str) -> str:
    lang_name(code)
    return LANGUAGES[code]["disclosure"]
