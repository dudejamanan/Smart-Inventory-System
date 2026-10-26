"""Explicitly sends a Telegram test. Credentials are read privately from .env."""

import argparse
from pathlib import Path
from common import Config
from app.services.notifier import TelegramNotifier


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--photo")
    p.add_argument(
        "--chat-id",
        action="store_true",
        help="Read recent bot messages to find your private chat ID; does not send",
    )
    args = p.parse_args()
    c = Config()
    if not c.telegram_bot_token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env first")
    notifier = TelegramNotifier(c)
    try:
        if args.chat_id:
            response = notifier.client.get(
                f"https://api.telegram.org/bot{c.telegram_bot_token}/getUpdates"
            )
            response.raise_for_status()
            chats = {
                v["message"]["chat"]["id"]
                for v in response.json().get("result", [])
                if "message" in v
            }
            print("Recent chat IDs:", sorted(chats))
            return
        if not c.telegram_chat_id:
            raise ValueError("Set TELEGRAM_CHAT_ID in .env")
        print("Text:", notifier.send("Warehouse: explicit operator notification test"))
        if args.photo:
            print(
                "Photo:",
                notifier.send("Warehouse test photo", str(Path(args.photo).resolve())),
            )
    except Exception as exc:
        raise SystemExit(
            f"Telegram test failed ({type(exc).__name__}); check credentials/connectivity privately"
        ) from None
    finally:
        notifier.client.close()


if __name__ == "__main__":
    main()
