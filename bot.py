import os
import requests
import logging
import time
import re
import json
from datetime import datetime
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# --- CONFIG & INITIALIZATION ---
# --- CONFIG & INITIALIZATION ---
TOKEN = os.getenv("BOT_TOKEN")
IFTTT_KEY = os.getenv("IFTTT_KEY")
LOG_CHAT_ID = os.getenv("LOG_CHAT_ID")
EVENT_NAME = "add_spotify_song"

START_TIME = time.time()
INTERACTIONS_COUNT = 0

START_TIME = time.time()
INTERACTIONS_COUNT = 0

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("AOTY_O2S")

# --- MONITORING UTILITIES ---

def get_readable_time(seconds: int) -> str:
    count = 0
    time_suffix_list = ["s", "m", "h", "days"]
    time_list = []
    while count < 4:
        count += 1
        if count < 3:
            remainder, result = divmod(seconds, 60)
        else:
            remainder, result = divmod(seconds, 24)
        if seconds == 0 and remainder == 0: break
        time_list.append(int(result))
        seconds = remainder
    return " ".join([f"{val}{suffix}" for val, suffix in zip(reversed(time_list), reversed(time_suffix_list[:len(time_list)]))])
# --- MONITORING UTILITIES ---

def get_readable_time(seconds: int) -> str:
    count = 0
    time_suffix_list = ["s", "m", "h", "days"]
    time_list = []
    while count < 4:
        count += 1
        if count < 3:
            remainder, result = divmod(seconds, 60)
        else:
            remainder, result = divmod(seconds, 24)
        if seconds == 0 and remainder == 0: break
        time_list.append(int(result))
        seconds = remainder
    return " ".join([f"{val}{suffix}" for val, suffix in zip(reversed(time_list), reversed(time_suffix_list[:len(time_list)]))])

def send_telegram_log(message):
    if not LOG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": LOG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    payload = {"chat_id": LOG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        logger.error(f"Failed to send Telegram log: {e}")

# --- DATA EXTRACTION ---

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
        id_match = re.search(r'spotify\.com/(?:album|track|s)/([a-zA-Z0-9]+)', spotify_url)
        spotify_id = id_match.group(1) if id_match else spotify_data.get('entityUniqueId', '').split('::')[-1]

        if content_type == 'song':
            return 'song', title, artist, [spotify_id]

        # Album Unpacking
        embed_url = f"https://open.spotify.com/embed/album/{spotify_id}"
        response = requests.get(embed_url, headers={'User-Agent': 'Mozilla/5.0'})
        pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
        match = re.search(pattern, response.text)
        
        if match:
            data = json.loads(match.group(1))
            album_data = data['props']['pageProps']['state']['data']['entity']
            track_ids = [t['uri'].split(':')[-1] for t in album_data.get('trackList', [])]
            return 'album', title, artist, track_ids
            
        return 'album', title, artist, []
    except Exception as e:
        logger.exception("Error during metadata extraction")
        logger.exception("Error during metadata extraction")
        return None, "Error", "Error", []

# --- CORE HANDLER ---

# --- CORE HANDLER ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global INTERACTIONS_COUNT
    INTERACTIONS_COUNT += 1
    
    global INTERACTIONS_COUNT
    INTERACTIONS_COUNT += 1
    
    msg = update.channel_post or update.message
    if not msg or not msg.text:
        return

    url = next((w for w in msg.text.split() if "http" in w), None)
    
    if url and any(domain in url for domain in ["album.link", "odesli.co", "song.link"]):
        start_proc = time.time()
        logger.info(f"Interaction #{INTERACTIONS_COUNT}: Processing {url}")
        start_proc = time.time()
        logger.info(f"Interaction #{INTERACTIONS_COUNT}: Processing {url}")
        
        content_type, title, artist, track_ids = get_spotify_data(url)
        
        if not track_ids:
            send_telegram_log(f"⚠️ *Failed:* No Spotify tracks found for {url}")
            send_telegram_log(f"⚠️ *Failed:* No Spotify tracks found for {url}")
            return

        success_count = 0
        for tid in track_ids:
            ifttt_url = f"https://maker.ifttt.com/trigger/{EVENT_NAME}/with/key/{IFTTT_KEY}"
            try:
                response = requests.post(ifttt_url, json={"value1": tid})
                response = requests.post(ifttt_url, json={"value1": tid})
                if response.status_code == 200:
                    success_count += 1
            except Exception as e:
                logger.error(f"IFTTT Connection Error: {e}")
                logger.error(f"IFTTT Connection Error: {e}")
            
            time.sleep(2)

        proc_duration = round(time.time() - start_proc, 2)
        
        if success_count == len(track_ids):
        proc_duration = round(time.time() - start_proc, 2)
        
        if success_count == len(track_ids):
            log_msg = (
                f"✅ *Successful Upload*\n"
                f"🎵 *Name:* {title}\n"
                f"👤 *Artist:* {artist}\n"
                f"🔢 *Tracks:* {success_count}/{len(track_ids)}\n"
                f"⏱ *Process Time:* {proc_duration}s"
                f"🔢 *Tracks:* {success_count}/{len(track_ids)}\n"
                f"⏱ *Process Time:* {proc_duration}s"
            )
        else:
            log_msg = (
                f"❌ *Partial Upload*\n"
                f"❌ *Partial Upload*\n"
                f"🎵 *Name:* {title}\n"
                f"👤 *Artist:* {artist}\n"
                f"⚠️ *Status:* {success_count}/{len(track_ids)} tracks added.\n"
                f"⏱ *Process Time:* {proc_duration}s"
                f"⚠️ *Status:* {success_count}/{len(track_ids)} tracks added.\n"
                f"⏱ *Process Time:* {proc_duration}s"
            )
        
        send_telegram_log(log_msg)
        
        send_telegram_log(log_msg)

# --- STARTUP ---

# --- STARTUP ---

if __name__ == '__main__':
    if not TOKEN or not IFTTT_KEY:
        logger.error("Missing Environment Variables!")
        logger.error("Missing Environment Variables!")
        exit(1)

    app = ApplicationBuilder().token(TOKEN).build()
    
    
    message_filter = (filters.TEXT & (~filters.COMMAND)) | filters.ChatType.CHANNEL
    app.add_handler(MessageHandler(message_filter, handle_message))
    
    boot_msg = (
        f"🚀 *Bot Backend Online*\n"
        f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📍 Env: Local Docker Container"
    )
    send_telegram_log(boot_msg)
    
    logger.info("Bot is active. Monitoring for links...")
    boot_msg = (
        f"🚀 *Bot Backend Online*\n"
        f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📍 Env: Local Docker Container"
    )
    send_telegram_log(boot_msg)
    
    logger.info("Bot is active. Monitoring for links...")
    app.run_polling()
