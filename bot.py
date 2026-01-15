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
EVENT_NAME = "add_spotify_song"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("AOTY_O2S")

# --- UNIVERSAL TRACK ID EXTRACTOR ---
def get_spotify_track_ids(url):
    try:
        api_url = f"https://api.song.link/v1-alpha.1/links?url={url}"
        r = requests.get(api_url).json()
        
        spotify_data = r.get('linksByPlatform', {}).get('spotify', {})
        spotify_url = spotify_data.get('url')
        
        if not spotify_url:
            logger.warning(f"Could not find a Spotify equivalent for: {url}")
            return []

        spotify_id_match = re.search(r'spotify\.com/(?:album|track|s)/([a-zA-Z0-9]+)', spotify_url)
        if not spotify_id_match:
            spotify_id = spotify_data.get('entityUniqueId', '').split('::')[-1]
        else:
            spotify_id = spotify_id_match.group(1)

        main_id = r.get('entityUniqueId')
        main_info = r.get('entitiesByUniqueId', {}).get(main_id, {})

        if main_info.get('type') == 'song':
            return [spotify_id]

        embed_url = f"https://open.spotify.com/embed/album/{spotify_id}"
        response = requests.get(embed_url, headers={'User-Agent': 'Mozilla/5.0'})
        pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
        match = re.search(pattern, response.text)
        
        if match:
            data = json.loads(match.group(1))
            album_data = data['props']['pageProps']['state']['data']['entity']
            track_ids = [t['uri'].split(':')[-1] for t in album_data.get('trackList', [])]
            return track_ids
            
        return []
    except Exception as e:
        logger.error(f"Error fetching IDs: {e}")
        return []

# --- MESSAGE HANDLER ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post or update.message
    if not msg or not msg.text:
        return

    url = next((w for w in msg.text.split() if "http" in w), None)
    
    if url and any(domain in url for domain in ["album.link", "odesli.co", "song.link"]):
        logger.info(f"📡 Processing link: {url}")
        track_ids = get_spotify_track_ids(url)
        
        if not track_ids:
            return

        for tid in track_ids:
            ifttt_url = f"https://maker.ifttt.com/trigger/{EVENT_NAME}/with/key/{IFTTT_KEY}"
            payload = {"value1": tid}
            try:
                response = requests.post(ifttt_url, json=payload)
                if response.status_code == 200:
                    logger.info(f"🚀 Sent to IFTTT: {tid}")
            except Exception as e:
                logger.error(f"❌ Connection Error: {e}")
            
            time.sleep(2)

if __name__ == '__main__':
    if not TOKEN or not IFTTT_KEY:
        logger.error("Missing Environment Variables (BOT_TOKEN or IFTTT_KEY)")
        exit(1)

    app = ApplicationBuilder().token(TOKEN).build()
    message_filter = (filters.TEXT & (~filters.COMMAND)) | filters.ChatType.CHANNEL
    app.add_handler(MessageHandler(message_filter, handle_message))
    
    logger.info("Bot is active. Polling for links...")
    app.run_polling()
