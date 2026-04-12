# FurnaceRadarBot (AOTY_O2S_BOT) — Project Guidelines

## Architecture

Single-file Python bot (`bot.py`). All logic lives here — no modules, no packages.
Pipeline: Telegram update -> message text parsing -> Spotify URL extraction (album/track) -> track ID expansion -> IFTTT Webhook per track.

**Key functions:**
- `get_spotify_tracks(spotify_url)` — parses Spotify URLs and returns a list of track IDs
- `handle_message(update, context)` — async Telegram handler; entry point for every message
- `send_telegram_log(message, silent)` — operational monitoring via `LOG_CHAT_ID`

## Function Deep Dive

### send_telegram_log(message, silent=False)

Purpose:
- Sends operational logs to the configured Telegram log chat.

Behavior:
- Returns immediately when `LOG_CHAT_ID` is not set.
- Calls Telegram Bot API endpoint `sendMessage` with `parse_mode=Markdown`.
- Uses `disable_notification` for silent progress updates.
- Swallows network failures and writes an error to the Python logger.

Inputs:
- `message`: text content sent to the log chat.
- `silent`: controls push notification behavior for noisy progress logs.

Side effects:
- Outbound HTTP POST to Telegram API.

### get_spotify_tracks(spotify_url)

Purpose:
- Converts one Spotify album/track URL into one or many track IDs for IFTTT.

Behavior:
- Uses regex to validate and parse `open.spotify.com/(album|track)/<id>` links.
- For `track` URLs, returns a one-item list with the parsed track ID.
- For `album` URLs, fetches Spotify embed page and reads `__NEXT_DATA__` JSON payload.
- Extracts each `trackList` item URI and converts `spotify:track:<id>` to `<id>`.
- Returns empty list when parsing fails, URL is unsupported, or extraction errors happen.

Inputs:
- `spotify_url`: canonical Spotify web URL included in message text.

Return contract:
- `[{"id": "<spotify_track_id>"}, ...]`
- Empty list means "do not proceed with IFTTT upload".

Failure handling:
- Any exception is logged and converted to an empty result.

### handle_message(update, context)

Purpose:
- Main workflow coordinator for each Telegram update.

Behavior:
- Increments `INTERACTIONS_COUNT` for lightweight traffic tracking.
- Selects message source from either `update.channel_post` or `update.message`.
- Ignores updates with no text payload.
- Extracts first Spotify album/track URL from message text via regex.
- Calls `get_spotify_tracks`; aborts and logs failure when no tracks found.
- Sends "STARTING PROCESSING" log with track count.
- Iterates tracks in order and triggers IFTTT event `add_spotify_song` using `value1=<track_id>`.
- Sleeps `2` seconds between requests to preserve playlist insertion order and reduce race conditions.
- Sends a final completion log with success count and duration.

Inputs:
- `update`: Telegram update object.
- `context`: PTB context object (currently unused but preserved by handler signature).

Side effects:
- Outbound HTTP requests to IFTTT and Telegram APIs.
- Blocking delay (`time.sleep(2)`) inside async handler, intentional for serial ordering.

## App Startup Flow (__main__)

Startup sequence:
1. Validate required env vars: `BOT_TOKEN`, `IFTTT_KEY`.
2. Exit process when required vars are missing.
3. Build Telegram app with `ApplicationBuilder().token(TOKEN).build()`.
4. Register one `MessageHandler` with combined filter:
	- text messages excluding commands
	- channel posts
5. Send backend-online log with current timestamp.
6. Start long-running poller with `app.run_polling()`.

Operational meaning of app startup:
- The app runs as a polling worker (not webhook server).
- A single process handles parsing, extraction, and upload serially.
- Any restart resets in-memory counters (`START_TIME`, `INTERACTIONS_COUNT`).

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `BOT_TOKEN` | Yes | Telegram bot token from @BotFather |
| `IFTTT_KEY` | Yes | IFTTT Maker Webhooks key |
| `LOG_CHAT_ID` | No | Telegram chat ID for operational logs |
| `MUSIC_RADAR_THREAD_ID` | No | `message_thread_id` of the Music Radar forum topic. When set, messages from all other topics are silently ignored. Leave unset to process all topics (backwards-compatible). |

The bot exits at startup if `BOT_TOKEN` or `IFTTT_KEY` are missing.

## Build and Run

```bash
# Local (requires .env file or exported env vars)
pip install -r requirements.txt
python bot.py

# Docker (preferred)
docker-compose up --build
```

Uses `polling` mode (`app.run_polling()`), not webhooks.

## Conventions

- **No test suite** — validate changes by running the bot locally against a test Telegram channel.
- **2-second sleep between IFTTT calls** (`time.sleep(2)`) is intentional — preserves "Date Added" order in Spotify and prevents IFTTT race conditions. Do not remove it.
- IFTTT event name is hardcoded as `"add_spotify_song"` (`EVENT_NAME` constant).
- Monitoring is done through Telegram messages (`send_telegram_log`), not stdout — check `LOG_CHAT_ID` logs when debugging production issues.

## Known Fragility

- **Spotify embed scraping** (`__NEXT_DATA__` JSON blob from `open.spotify.com/embed/album/...`) can break if Spotify changes their embed page structure. If album track extraction stops working, this is the first place to check.
- URL parser currently accepts only canonical `open.spotify.com/album/...` and `open.spotify.com/track/...` links. Short links and alternate forms are ignored.
