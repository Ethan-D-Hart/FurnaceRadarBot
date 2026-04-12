import os
import requests
import logging
import time
import re
import json
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# --- CONFIG & INITIALIZATION ---
TOKEN = os.getenv("BOT_TOKEN")
IFTTT_KEY = os.getenv("IFTTT_KEY")
LOG_CHAT_ID = os.getenv("LOG_CHAT_ID")
EVENT_NAME = "add_spotify_song"

# Optional: restrict processing to a specific Telegram forum topic.
# Set to the integer message_thread_id of the Music Radar topic.
# Leave unset to process messages from all topics (backwards-compatible).
_raw_thread_id = os.getenv("MUSIC_RADAR_THREAD_ID")
MUSIC_RADAR_THREAD_ID = int(_raw_thread_id) if _raw_thread_id else None

START_TIME = time.time()
INTERACTIONS_COUNT = 0

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("AOTY_O2S")

# --- MONITORING UTILITIES ---

def send_telegram_log(message, silent=False):
    """Sends a plain text log message to your private group/chat."""
    if not LOG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": LOG_CHAT_ID, 
        "text": message, 
        "parse_mode": "Markdown",
        "disable_notification": silent
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        logger.error(f"Failed to send Telegram log: {e}")

# --- DATA EXTRACTION ---

def extract_spotify_url(text):
    """Scans raw message text for the first Spotify album or track URL.
    Returns the URL string, or None if no match is found.
    """
    match = re.search(r'(https?://open\.spotify\.com/(?:album|track)/[a-zA-Z0-9]+)', text)
    return match.group(1) if match else None


def extract_message_date(text):
    """Looks for a MM/DD/YYYY date anywhere in the message text.

    This matches the expected message format where the release date appears
    as its own line, e.g. '12/31/2025'. Returns a datetime if found,
    or datetime.now() as a fallback so playlist routing always succeeds.
    """
    match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', text)
    if match:
        try:
            return datetime(int(match.group(3)), int(match.group(1)), int(match.group(2)))
        except ValueError:
            pass
    return datetime.now()


def _fetch_album_tracks(spotify_id):
    """Fetches the Spotify embed page for an album and extracts the track list
    by parsing the embedded __NEXT_DATA__ JSON payload.

    This approach relies on Spotify's embed page structure — if they change
    __NEXT_DATA__, this will break. See 'Known Fragility' in the project docs.

    Returns a list of dicts like [{"id": "<track_id>"}, ...], or [] on failure.
    """
    embed_url = f"https://open.spotify.com/embed/album/{spotify_id}"
    response = requests.get(embed_url, headers={'User-Agent': 'Mozilla/5.0'})

    # The embed page embeds all album data in a JSON blob inside a <script> tag
    pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
    embed_match = re.search(pattern, response.text)
    if not embed_match:
        return []

    data = json.loads(embed_match.group(1))
    album_data = data['props']['pageProps']['state']['data']['entity']

    # Each track URI looks like "spotify:track:<id>" — we only need the trailing ID
    return [
        {"id": t['uri'].split(':')[-1]}
        for t in album_data.get('trackList', [])
    ]


def get_spotify_tracks(spotify_url):
    """Resolves a Spotify album or track URL to a list of track IDs.

    For a track URL  -> returns a one-item list immediately.
    For an album URL -> delegates to _fetch_album_tracks to scrape the embed page.

    Returns [] when the URL is unsupported, parsing fails, or an error occurs.
    The caller should treat an empty list as "do not proceed".
    """
    try:
        match = re.search(r'open\.spotify\.com/(album|track)/([a-zA-Z0-9]+)', spotify_url)
        if not match:
            return []

        content_type, spotify_id = match.group(1), match.group(2)

        if content_type == 'track':
            # Single-track URL — no network call needed
            return [{"id": spotify_id}]

        # Album URL — fetch all tracks from the embed page
        return _fetch_album_tracks(spotify_id)

    except Exception:
        logger.exception("Error during Spotify track extraction")
        return []

# --- IFTTT INTEGRATION ---

def trigger_ifttt(track_id, playlist_name):
    """Fires a single IFTTT Maker Webhook for the given Spotify track ID.

    The track ID is passed as `value1` and the target playlist name as `value2`
    so the IFTTT applet can dynamically route the track to the correct playlist.
    Returns True when IFTTT accepted the request (HTTP 200), False otherwise.
    """
    print(f"Triggering IFTTT for track {track_id} -> playlist '{playlist_name}'")
    url = f"https://maker.ifttt.com/trigger/{EVENT_NAME}/with/key/{IFTTT_KEY}"
    response = requests.post(url, json={"value1": track_id, "value2": playlist_name})
    return response.status_code == 200


def upload_tracks(tracks, playlist_name):
    """Iterates a list of track dicts, triggering one IFTTT webhook per track.

    A 2-second sleep between calls is intentional — it preserves the "Date Added"
    order in Spotify and avoids IFTTT race conditions. Do not remove it.

    Returns the number of tracks successfully accepted by IFTTT.
    """
    success_count = 0
    total = len(tracks)

    for i, track in enumerate(tracks, 1):
        tid = track['id']
        try:
            if trigger_ifttt(tid, playlist_name):
                success_count += 1
                # Send a silent progress ping so the log chat stays updated
                # without triggering a notification for every single track
                if total > 1:
                    send_telegram_log(f"Uploaded ({i}/{total})", silent=True)
        except Exception as e:
            logger.error(f"IFTTT connection error for track {tid}: {e}")

        # Wait between requests to maintain correct playlist insertion order
        time.sleep(2)

    return success_count


# --- CORE HANDLER ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for every Telegram message/channel post received by the bot.

    High-level flow:
      1. Ignore updates that carry no text.
      2. Look for a Spotify URL in the message.
      3. Resolve the URL to a list of track IDs.
      4. Upload each track to IFTTT and log progress.
      5. Send a final summary log.
    """
    global INTERACTIONS_COUNT
    INTERACTIONS_COUNT += 1

    # Accept both channel posts and regular messages
    msg = update.channel_post or update.message
    if not msg or not msg.text:
        return

    # Topic filtering: when MUSIC_RADAR_THREAD_ID is configured, only process
    # messages from that forum thread and silently drop everything else.
    if MUSIC_RADAR_THREAD_ID is not None:
        if msg.message_thread_id != MUSIC_RADAR_THREAD_ID:
            return
    else:
        # Discovery mode: log the thread ID so the operator can configure it.
        send_telegram_log(
            f"ℹ️ MUSIC_RADAR_THREAD_ID not set.\n"
            f"Current message thread ID: `{msg.message_thread_id}`\n"
            f"Set this value in your .env to restrict processing to one topic.",
            silent=True
        )

    # Bail out early if the message contains no Spotify link
    spotify_url = extract_spotify_url(msg.text)
    if not spotify_url:
        return

    start_proc = time.time()

    # Resolve URL -> list of track IDs (may require an outbound Spotify request)
    tracks = get_spotify_tracks(spotify_url)
    if not tracks:
        send_telegram_log(f"FAILED: No tracks found for {spotify_url}")
        return

    # Derive the target playlist from the date in the message (falls back to today)
    ref_date = extract_message_date(msg.text)
    playlist_name = ref_date.strftime("Furnace Radar %Y - %B")

    # Notify the log chat that processing is starting
    send_telegram_log(
        f"STARTING PROCESSING\n"
        f"Playlist: {playlist_name}\n"
        f"Tracks: {len(tracks)}"
    )

    # Upload every track to IFTTT, applying the inter-request delay
    success_count = upload_tracks(tracks, playlist_name)

    proc_duration = round(time.time() - start_proc, 2)

    # Summarise the outcome — distinguish full success from partial failures
    status = "FINISHED" if success_count == len(tracks) else "PARTIAL COMPLETION"
    send_telegram_log(
        f"{status}\n"
        f"Status: {success_count}/{len(tracks)} tracks added\n"
        f"Duration: {proc_duration}s"
    )

if __name__ == '__main__':
    # Fail fast when required credentials are absent — the bot cannot function without them
    if not TOKEN or not IFTTT_KEY:
        logger.error("Missing required environment variables: BOT_TOKEN and/or IFTTT_KEY")
        exit(1)

    app = ApplicationBuilder().token(TOKEN).build()

    # Listen for plain text messages (regular chats) and all channel posts
    message_filter = (filters.TEXT & (~filters.COMMAND)) | filters.ChatType.CHANNEL
    app.add_handler(MessageHandler(message_filter, handle_message))

    # Announce that the backend is live so the log chat confirms a clean startup
    send_telegram_log(f"BOT BACKEND ONLINE - {datetime.now().strftime('%H:%M:%S')}")

    # Run in long-polling mode (no webhook server required)
    app.run_polling()