# Optional Telegram channel

WhatsApp remains the requested default. Telegram provides an independent optional alert channel with text and multipart JPEG upload; no public photo URL or inbound tunnel is needed. See the [official Bot API](https://core.telegram.org/bots/api#sendphoto).

1. In Telegram open the verified @BotFather account, use /newbot, choose its name and username, and copy the bot token privately into TELEGRAM_BOT_TOKEN in .env. Never paste it into chat or a screenshot.
2. Open your new bot from your receiving account and send /start or hello. Bots cannot initiate a private conversation until you contact them.
3. With the backend stopped, run `python tools/telegram_test.py --chat-id`. It reads recent bot updates and prints chat IDs locally; identify your own test conversation and set TELEGRAM_CHAT_ID in .env. Do not configure an external webhook/poller for the same bot while using this lookup. Avoid adding the bot to unrelated groups.
4. Set NOTIFY_CHANNELS=telegram,whatsapp to use both, or telegram for Telegram alone. A blank channel list disables real notifications. Restart the backend. Telegram and WhatsApp have separate workers, three-attempt retry/backoff and per-kind 20-second suppression. Provider delivery statuses appear on the incident.
5. Explicitly send a test with `python tools/telegram_test.py --photo data/gate-check.jpg`. Verify actual receipt. Keep the laptop connected to the internet; Telegram failure cannot block RFID or the buzzer.
6. If compromised, revoke the token in BotFather, replace it privately in .env and restart. Uploaded evidence reaches Telegram and the receiving account; obtain consent and delete test images when appropriate. No real Telegram delivery was tested during development.
