"""Speak locally through the same isolated worker; no RFID/alarm/provider effects."""

import argparse
import time
from common import Config
from app.services.speech import SpeechQueue


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--text", default="Voice test. Access granted. Access denied. Security alarm."
    )
    args = p.parse_args()
    c = Config()
    if not c.tts_enabled:
        raise SystemExit(
            "Speech is muted. Set TTS_ENABLED=true or enable it in the dashboard."
        )
    speech = SpeechQueue(c)
    try:
        speech.start()
        speech.say("manual-test", args.text, ttl=20)
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            status = speech.status()
            if status["error"]:
                raise SystemExit(status["error"])
            if status["completed"]:
                print(
                    "PASS: speech engine completed the utterance. Confirm audible output on the laptop."
                )
                print("Available voices:", [v["name"] for v in status["voices"]])
                return
            time.sleep(0.05)
        raise SystemExit(
            "Speech did not complete in time; inspect the laptop audio/voice driver."
        )
    finally:
        speech.close()


if __name__ == "__main__":
    main()
