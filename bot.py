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

def get_spotify_data(url):
    try:
        api_url = f"https://api.song.link/v1-alpha.1/links?url={url}"
        r = requests.get(api_url).json()
        
        main_id = r.get('entityUniqueId')
        main_info = r.get('entitiesByUniqueId', {}).get(main_id, {})
        title = main_info.get('title', 'Unknown Title')
        artist = main_info.get('artistName', 'Unknown Artist')
        content_type = main_info.get('type', 'song')

        spotify_data = r.get('linksByPlatform', {}).get('spotify', {})
        spotify_url = spotify_data.get('url')
        
        if not spotify_url:
            return content_type, title, artist, []

        id_match = re.search(r'spotify\.com/(?:album|track|s)/([a-zA-Z0-9]+)', spotify_url)
        spotify_id = id_match.group(1) if id_match else spotify_data.get('entityUniqueId', '').split('::')[-1]

        if content_type == 'song':
            return 'song', title, artist, [{"id": spotify_id, "name": title}]

        embed_url = f"https://open.spotify.com/embed/album/{spotify_id}"
        response = requests.get(embed_url, headers={'User-Agent': 'Mozilla/5.0'})
        pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
        match = re.search(pattern, response.text)
        
        if match:
            data = json.loads(match.group(1))
            album_data = data['props']['pageProps']['state']['data']['entity']
            track_list = []
            for t in album_data.get('trackList', []):
                track_list.append({
                    "id": t['uri'].split(':')[-1],
                    "name": t.get('trackTitle', 'Unknown Track')
                })
            return 'album', title, artist, track_list
            
        return 'album', title, artist, []
    except Exception as e:
        logger.exception("Error during metadata extraction")
        return None, "Error", "Error", []

# --- CORE HANDLER ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global INTERACTIONS_COUNT
    INTERACTIONS_COUNT += 1
    
    msg = update.channel_post or update.message
    if not msg or not msg.text:
        return

    url = next((w for w in msg.text.split() if "http" in w), None)
    
    if url and any(domain in url for domain in ["album.link", "odesli.co", "song.link"]):
        start_proc = time.time()
        
        content_type, title, artist, tracks = get_spotify_data(url)
        
        if not tracks:
            send_telegram_log(f"FAILED: No Spotify content found for {url}")
            return

        # 1. PRE-UPLOAD LOG
        send_telegram_log(
            f"STARTING PROCESSING\n"
            f"Name: {title} by {artist}\n"
            f"Tracks: {len(tracks)}"
        )

        success_count = 0
        for i, track in enumerate(tracks, 1):
            tid = track['id']

            ifttt_url = f"https://maker.ifttt.com/trigger/{EVENT_NAME}/with/key/{IFTTT_KEY}"
            try:
                response = requests.post(ifttt_url, json={"value1": tid})
                if response.status_code == 200:
                    success_count += 1
                    # 2. INDIVIDUAL TRACK LOG (SILENT)
                    if len(tracks) > 1:
                        send_telegram_log(f"Uploaded ({i}/{len(tracks)})", silent=True)
            except Exception as e:
                logger.error(f"IFTTT Connection Error: {e}")
            
            time.sleep(2)

        proc_duration = round(time.time() - start_proc, 2)
        
        # FINAL SUMMARY LOG
        status = "FINISHED" if success_count == len(tracks) else "PARTIAL COMPLETION"
        send_telegram_log(
            f"{status}\n"
            f"Name: {title}\n"
            f"Status: {success_count}/{len(tracks)} tracks added\n"
            f"Duration: {proc_duration}s"
        )

if __name__ == '__main__':
    if not TOKEN or not IFTTT_KEY:
        logger.error("Missing Environment Variables!")
        exit(1)

    app = ApplicationBuilder().token(TOKEN).build()
    message_filter = (filters.TEXT & (~filters.COMMAND)) | filters.ChatType.CHANNEL
    app.add_handler(MessageHandler(message_filter, handle_message))
    
    send_telegram_log(f"BOT BACKEND ONLINE - {datetime.now().strftime('%H:%M:%S')}")
    app.run_polling()