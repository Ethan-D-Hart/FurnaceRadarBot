import os
import requests
import logging
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- DUMMY SERVER FOR KOYEB HEALTH CHECK ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

    def log_message(self, format, *args):
        return # Silence logs from the dummy server

def run_health_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"🕸️ Health check server started on port {port}")
    server.serve_forever()

# --- CONFIG ---
TOKEN = "8542325435:AAHCPZQg5j0EmGx7W9N6KpIYmNcdtH83p70"
IFTTT_KEY = "tx1qmZkEiRz4WQ_T7o3oL"
EVENT_NAME = "add_spotify_song"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("AOTY_O2S")

def get_tracks_from_entities(odesli_url):
    """Extracts all song titles from the native Odesli response entities"""
    try:
        api_url = f"https://api.song.link/v1-alpha.1/links?url={odesli_url}"
        r = requests.get(api_url).json()
        
        # Get the main album artist to filter out random 'related' songs
        main_entity_id = r.get('entityUniqueId')
        main_info = r.get('entitiesByUniqueId', {}).get(main_entity_id, {})
        album_artist = main_info.get('artistName', '').lower()
        album_title = main_info.get('title', '').lower()

        logger.info(f"🔍 Analyzing Album Entities: {album_title} by {album_artist}")

        tracks = []
        seen_titles = set()

        # Odesli returns a list of 'entitiesByUniqueId'
        # For albums, this OFTEN contains the individual songs if they are available
        entities = r.get('entitiesByUniqueId', {})
        
        for eid, info in entities.items():
            # We only want 'song' types
            if info.get('type') == 'song':
                title = info.get('title')
                artist = info.get('artistName')
                
                # Verify it's actually by the same artist and not a duplicate
                if album_artist in artist.lower() and title.lower() not in seen_titles:
                    tracks.append({"title": title, "artist": artist})
                    seen_titles.add(title.lower())
        
        # FALLBACK: If Odesli didn't list the songs, we use the iTunes search as a last resort
        if not tracks:
            logger.info("No songs found in Odesli entities. Trying iTunes fallback...")
            itunes_url = f"https://itunes.apple.com/search?term={album_title} {album_artist}&entity=song&limit=40"
            it_res = requests.get(itunes_url).json()
            for item in it_res.get('results', []):
                if album_title in item.get('collectionName', '').lower() and item.get('trackName').lower() not in seen_titles:
                    tracks.append({"title": item.get('trackName'), "artist": item.get('artistName')})
                    seen_titles.add(item.get('trackName').lower())

        return tracks

    except Exception as e:
        logger.error(f"❌ Error extracting tracks: {e}")
        return []

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    url = next((w for w in text.split() if "http" in w), None)
    
    if url and any(domain in url for domain in ["album.link", "odesli.co", "song.link"]):
        msg = await update.message.reply_text("📡 Connecting to Odesli...")
        
        tracks = get_tracks_from_entities(url)
        
        if not tracks:
            await msg.edit_text("❌ Could not extract a tracklist for this album.")
            return

        await msg.edit_text(f"📦 Found {len(tracks)} tracks. Sending to Spotify...")
        
        success = 0
        for i, track in enumerate(tracks):
            # The Trigger
            ifttt_url = f"https://maker.ifttt.com/trigger/{EVENT_NAME}/with/key/{IFTTT_KEY}"
            payload = {"value1": track['title'], "value2": track['artist']}
            
            try:
                res = requests.post(ifttt_url, json=payload)
                if res.status_code == 200:
                    success += 1
                    logger.info(f"[{success}/{len(tracks)}] Sent: {track['title']}")
            except:
                logger.error(f"Failed to send {track['title']}")

            time.sleep(0.6) # Safe delay

        await update.message.reply_text(f"✅ Mission Complete. Added {success} songs.")

if __name__ == '__main__':
    # 1. Start the Health Check server in a background thread
    threading.Thread(target=run_health_server, daemon=True).start()

    # 2. Start the Telegram Bot
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("add", add_album))
    logger.info("Cloud Bot is online with Health Check bypass...")
    app.run_polling()
