import os
import requests
import logging
import time
import re
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN")
IFTTT_KEY = os.getenv("IFTTT_KEY")
LOG_CHAT_ID = os.getenv("LOG_CHAT_ID")
EVENT_NAME = "add_spotify_song"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("AOTY_O2S")


def send_telegram_log(message):
    """Sends a log message to a specific Telegram chat/channel."""
    if not LOG_CHAT_ID:
        return
        
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": LOG_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        requests.post(url, json=payload)
    except Exception as e:
        logger.error(f"Failed to send Telegram log: {e}")

# --- UNIVERSAL TRACK ID EXTRACTOR ---
def get_spotify_data(url):
    """Returns (type, title, artist, track_ids)"""
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

        spotify_id_match = re.search(r'spotify\.com/(?:album|track|s)/([a-zA-Z0-9]+)', spotify_url)
        spotify_id = spotify_id_match.group(1) if spotify_id_match else spotify_data.get('entityUniqueId', '').split('::')[-1]

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
        logger.error(f"Error fetching metadata: {e}")
        return None, "Error", "Error", []

# --- MESSAGE HANDLER ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post or update.message
    if not msg or not msg.text:
        return

    url = next((w for w in msg.text.split() if "http" in w), None)
    
    if url and any(domain in url for domain in ["album.link", "odesli.co", "song.link"]):
        logger.info(f"📡 Processing link: {url}")
        
        content_type, title, artist, track_ids = get_spotify_data(url)
        
        if not track_ids:
            send_telegram_log(f"❌ *Failed:* No Spotify tracks found for {url}")
            return

        success_count = 0
        total_tracks = len(track_ids)

        for tid in track_ids:
            ifttt_url = f"https://maker.ifttt.com/trigger/{EVENT_NAME}/with/key/{IFTTT_KEY}"
            payload = {"value1": tid}
            try:
                response = requests.post(ifttt_url, json=payload)
                if response.status_code == 200:
                    success_count += 1
                    logger.info(f"🚀 Sent to IFTTT: {tid}")
                else:
                    logger.error(f"IFTTT Error {response.status_code} for {tid}")
            except Exception as e:
                logger.error(f"❌ Connection Error: {e}")
            
            time.sleep(2)

        # Final Status Log
        if success_count == total_tracks:
            log_msg = (
                f"✅ *Successful Upload*\n"
                f"🎵 *Name:* {title}\n"
                f"👤 *Artist:* {artist}\n"
                f"🔢 *Tracks:* {success_count}/{total_tracks}"
            )
            send_telegram_log(log_msg)
        else:
            log_msg = (
                f"❌ *Failed/Partial Upload*\n"
                f"🎵 *Name:* {title}\n"
                f"👤 *Artist:* {artist}\n"
                f"⚠️ *Status:* {success_count}/{total_tracks} tracks added."
            )
            send_telegram_log(log_msg)

if __name__ == '__main__':
    if not TOKEN or not IFTTT_KEY:
        logger.error("Missing Environment Variables (BOT_TOKEN or IFTTT_KEY)")
        exit(1)

    app = ApplicationBuilder().token(TOKEN).build()
    message_filter = (filters.TEXT & (~filters.COMMAND)) | filters.ChatType.CHANNEL
    app.add_handler(MessageHandler(message_filter, handle_message))
    
    logger.info("Bot is active. Polling for links...")
    app.run_polling()