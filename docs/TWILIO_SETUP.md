# Twilio WhatsApp setup

## 1. Account and sandbox

1. Create your own account at [Twilio](https://www.twilio.com/), complete its phone/email checks and inspect trial/billing limits. Account creation and any charges are your responsibility; no credentials are bundled here.
2. Follow Twilio's [sandbox instructions](https://www.twilio.com/docs/whatsapp/sandbox). The current documentation distinguishes the legacy Console sandbox from the newer Console's **Try out WhatsApp** flow. Choose the testing environment available in your account; the menu names may differ. Confirm it provides your sandbox sender and join code.
3. From the **owner's** WhatsApp phone send `join <the exact code shown by Twilio>` to the sender number shown in the console (commonly +14155238886). Success: a sandbox join confirmation on the phone. Only joined recipients can receive sandbox messages. Rejoin if sandbox membership expires; the current documented membership period is three days.
4. Find Account SID and Auth Token in your Twilio account dashboard. Reveal/copy the token privately. Put them only in .env, never in a screenshot, report, source file or chat. Set:

```dotenv
TWILIO_ACCOUNT_SID=<your account SID>
TWILIO_AUTH_TOKEN=<your auth token>
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
OWNER_WHATSAPP_TO=whatsapp:+91<your complete number without spaces>
```

Replace all placeholders, including the example sender if your console differs. A recipient is E.164 format: country code and full number, prefixed by `whatsapp:`. Use your actual console's sandbox sender.

## 2. Public HTTPS access

Twilio downloads the JPEG itself. A localhost/LAN URL cannot work from Twilio's servers. Use an HTTPS tunnel to the **built backend on port 8000**, while keeping the phone camera stream private.

1. Set a strong admin password and signing secrets using `python scripts/init_env.py` before exposing the backend. Build the frontend. Start real mode or a deliberate simulator notification test with the intended data directory.
2. Install [ngrok](https://ngrok.com/docs/) through its official instructions, create/configure its account if required, and run `ngrok http 8000`. An alternative is [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/): after installing cloudflared, run `cloudflared tunnel --url http://localhost:8000` for a temporary development tunnel if supported by your environment.
3. Copy the generated `https://...` address into PUBLIC_BASE_URL in .env, **without a trailing path**. Keep MEDIA_URL_SECRET as the generated 64-character random value. Set COOKIE_SECURE=true if accessing the dashboard through HTTPS; then sign in through the HTTPS address, since secure cookies will not work on plain HTTP localhost.
4. Restart the backend after changing .env. Open the HTTPS address using phone mobile data (Wi-Fi off) to verify public reachability. Success: dashboard login loads. Do not bypass a tunnel's interstitial with query hacks; use a tunnel endpoint that Twilio can fetch directly.
5. The public endpoints are the two signed Twilio callbacks and HMAC JPEG tokens; other data requires admin login. Do not publish evidence directories or run a generic file server. Keep the tunnel running during tests.

## 3. Configure callbacks

1. In the sandbox's incoming message configuration, set **When a message comes in** to `https://YOUR-HOST/webhooks/twilio/inbound`, method **POST**, and save.
2. If the console offers a Status callback URL, set `https://YOUR-HOST/webhooks/twilio/status`, POST. The application also supplies this callback on each outbound SDK request.
3. Verify PUBLIC_BASE_URL matches the exact scheme/host used by Twilio. [Request signatures](https://www.twilio.com/docs/usage/security) depend on the full URL and form fields; a wrong host or token gives HTTP 403. Do not disable validation to solve this. Reverse proxies must preserve the configured public URL; the app deliberately ignores untrusted forwarded headers.
4. Send `hello` from the owner's WhatsApp phone to the sandbox **after** the inbound webhook is configured. Success: backend accepts the signed POST, and System health shows almost 24 hours remaining. Messages from other senders do not renew the owner's timer.

## 4. Session and delivery test

The current [Twilio 63016 reference](https://www.twilio.com/docs/api/errors/63016) identifies free-form sends outside the 24-hour service window. This project does not implement approved templates; it marks FAILED_SESSION_EXPIRED and asks the owner to send another message. A new inbound message renews the window. Sandbox membership expiry is a separate condition from this 24-hour window.

1. Keep the app/tunnel running and verify the positive session timer. Save a harmless test JPEG under data, for example with camera_test.py.
2. In a second terminal run `.\.venv\Scripts\python tools/twilio_test.py --photo data/gate-check.jpg` (Linux/macOS `.venv/bin/python ...`). **This command explicitly sends real messages** to your configured owner and may incur provider charges. Use your own sandbox recipient.
3. Success: the tool prints provider SIDs/statuses, the phone receives a text followed by a photo, and incident notification rows receive status updates. `queued` alone is not proof of phone delivery. Inspect the Twilio console message log if callbacks fail.
4. Trigger a deliberate third-failure or unattended-removal incident. Success: local buzzer occurs immediately, independent of network delay, while text/photo delivery happens later. Never repeat alarm tests around unaware people.
5. The app limits each incident kind to one alert per 20 s, spaces sandbox SDK requests at least 3.1 s apart, and retries failures up to three attempts with backoff. Rate-limited incidents still have logs/evidence and RATE_LIMITED notification rows.

## 5. Troubleshooting and shutdown

| Result | What to do |
|---|---|
| FAILED_SESSION_EXPIRED / 63016 | Owner sends hello; verify inbound webhook and timer; retry with a new test incident |
| 63015 / recipient not joined | Join the correct sandbox code again from the same recipient number |
| 401 / authentication failed | Check account SID/Auth Token, not API key credentials from a different setup |
| Webhook HTTP 403 | Exact public URL/token mismatch or invalid signature; compare console request URL |
| Text delivered, media failed | Check JPEG internet reachability, tunnel interstitial, 15-minute token expiry and MIME type |
| NO_PHOTO | Camera was unavailable; fix capture and test it locally first |
| RATE_LIMITED | Wait at least 20 s for that incident kind before a new test |
| Timer stays at zero | Wrong owner number, inbound webhook not saved, app using another data directory, or invalid signature |

Tokens bind one JPEG under the data directory and expire after 15 minutes. The app re-encodes outgoing photos to at most 1 MB. Delivery callback rows track SID, provider status, error and attempts. Stop the tunnel when finished. Rotate any credential accidentally shared; changing the media secret invalidates old URLs. Real delivery has not been verified without your account and phone.
