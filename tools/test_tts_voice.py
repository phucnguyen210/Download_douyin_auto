from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import load_settings
from app.services.tts_service import DEFAULT_TTS_VOICE_LABEL, TTSService, TTS_VOICE_OPTIONS


DEFAULT_TEXT = (
    "Em không ngờ anh lại che giấu thân phận lâu như vậy. "
    "Nếu hôm nay sự thật không bị phơi bày, tôi vẫn nghĩ mình chỉ là một người bị bỏ rơi."
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a short TTS sample for the selected voice.")
    parser.add_argument("--voice", default=DEFAULT_TTS_VOICE_LABEL, help="Voice label from TTS_VOICE_OPTIONS")
    parser.add_argument("--text", default=DEFAULT_TEXT, help="Vietnamese text used for the sample")
    parser.add_argument("--out", default="output/test_voice/tts_voice_test.wav", help="Output wav path")
    args = parser.parse_args()

    if args.voice not in TTS_VOICE_OPTIONS:
        labels = "\n".join(f"- {label}" for label in TTS_VOICE_OPTIONS)
        raise SystemExit(f"Unknown voice label: {args.voice}\nAvailable voices:\n{labels}")

    settings = load_settings()
    out_path = Path(args.out)
    service = TTSService(settings, voice_label=args.voice)
    service.synthesize_from_text(args.text, out_path)
    print(f"Voice: {args.voice}")
    print(f"Output: {out_path.resolve()}")


if __name__ == "__main__":
    main()

