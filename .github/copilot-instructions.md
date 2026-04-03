# Project Guidelines

## Code Style
- Primary code lives in `bot.py` and uses a single-module Python style with top-level constants for env/config.
- Keep logging consistent with `logging` + `logger` (`logging.basicConfig(...)` in `bot.py`) and operational Telegram logs via `send_telegram_log`.
- Preserve current async boundary: `handle_message` is async, while network calls are synchronous via `requests`.
- Follow existing parsing patterns (`re.search`, `dict.get`, defensive fallbacks) used in `get_spotify_data`.

## Architecture
- Bot is a Telegram-to-IFTTT bridge:
  1. Receive Telegram `message`/`channel_post` (`handle_message` in `bot.py`)
  2. Accept only Odesli/Songlink domains (`album.link`, `odesli.co`, `song.link`)
  3. Resolve canonical metadata via `https://api.song.link/v1-alpha.1/links`
  4. Expand Spotify album tracks from embed `__NEXT_DATA__`
  5. Send Spotify track IDs to IFTTT webhook event `add_spotify_song`
- Runtime is stateless and env-driven (`BOT_TOKEN`, `IFTTT_KEY`, optional `LOG_CHAT_ID`).

## Build and Test
- Install deps: `pip install -r requirements.txt`
- Run locally: `python bot.py`
- Build container: `docker build -t furnace-radar-bot .`
- Run with compose: `docker compose up -d`
- CI image pipeline is in `.github/workflows/docker-publish.yml`.
- There is no automated test suite in this repo; do not invent new test frameworks unless requested.

## Project Conventions
- Keep URL intake narrow: only process text containing `http` and supported Odesli domains (`handle_message` logic).
- Keep the 2-second inter-track delay (`time.sleep(2)`) to preserve ordering behavior in downstream playlist additions.
- Keep album-track extraction via Spotify embed JSON unless asked to replace with an API-based approach.
- Note current doc drift: `README.md` mentions HTTP health-check server/`PORT`, but `bot.py` currently does not implement it.

## Integration Points
- Telegram Bot SDK: `python-telegram-bot` (`ApplicationBuilder`, `MessageHandler`, `filters` in `bot.py`).
- Telegram HTTP API for private log messages: `https://api.telegram.org/bot<TOKEN>/sendMessage`.
- Odesli/Songlink API for link/entity resolution.
- Spotify embed page parsing for album track lists.
- IFTTT Maker webhook: `https://maker.ifttt.com/trigger/{EVENT_NAME}/with/key/{IFTTT_KEY}`.

## Security
- Treat `BOT_TOKEN`, `IFTTT_KEY`, and `LOG_CHAT_ID` as secrets; load from environment or `.env` used by `docker-compose.yaml`.
- Do not log secrets or include full webhook URLs in output.
- Prefer adding request timeouts for new HTTP calls; current code has no explicit timeout/retry policy.
- Keep CI signing/build flow intact in `.github/workflows/docker-publish.yml` (cosign + GHCR).
