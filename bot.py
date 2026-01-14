import os
import requests
import logging
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- 1. CONFIG ---
TOKEN = "8542325435:AAHCPZQg5j0EmGx7W9N6KpIYmNcdtH83p70"
IFTTT_KEY = "tx1qmZkEiRz4WQ_T7o3oL"
EVENT_NAME = "add_spotify_song"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("AOTY_O2S")

# --- 2. DUMMY SERVER FOR KOYEB ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive!")
    def log_message(self, format, *args):
        return

def run_health_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"🕸️ Health check server started on port {port}")
    server.serve_forever()

# --- 3. TRACK RETRIEVAL LOGIC ---
def get_tracks_from_entities(odesli_url):
    try:
        api_url = f"https://api.song.link/v1-alpha.1/links?url={odesli_url}"
        r = requests.get(api_url).json()
        main_id = r.get('entityUniqueId')
        main_info = r.get('entitiesByUniqueId', {}).get(main_id, {})
        album_artist = main_info.get('artistName', '').lower()
        album_title = main_info.get('title', '').lower()

        tracks = []
        seen_titles = set()
        entities = r.get('entitiesByUniqueId', {})
        for eid, info in entities.items():
            if info.get('type') == 'song':
                title = info.get('title')
                artist = info.get('artistName')
                if album_artist in artist.lower() and title.lower() not in seen_titles:
                    tracks.append({"title": title, "artist": artist})
                    seen_titles.add(title.lower())
        
        if not tracks:
            it_res = requests.get(f"https://itunes.apple.com/search?term={album_title} {album_artist}&entity=song&limit=40").json()
            for item in it_res.get('results', []):
                if album_title in item.get('collectionName', '').lower() and item.get('trackName').lower() not in seen_titles:
                    tracks.append({"title": item.get('trackName'), "artist": item.get('artistName')})
                    seen_titles.add(item.get('trackName').lower())
        return tracks
    except: return []

# --- 4. COMMAND HANDLER ---
async def add_album(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    url = context.args[0]
    
    if any(domain in url for domain in ["album.link", "odesli.co", "song.link"]):
        await update.message.react(reaction="⚡")
        
        tracks = get_tracks_from_entities(url)
        if not tracks: return

        for track in tracks:
            ifttt_url = f"https://maker.ifttt.com/trigger/{EVENT_NAME}/with/key/{IFTTT_KEY}"
            try:
                requests.post(ifttt_url, json={"value1": track['title'], "value2": track['artist']})
                logger.info(f"Added: {track['title']}")
            except: pass
            time.sleep(0.7)

# --- 5. MAIN STARTUP ---
if __name__ == '__main__':
    # Start health server thread
    threading.Thread(target=run_health_server, daemon=True).start()

    # Start Telegram Bot
    if not TOKEN:
        logger.error("BOT_TOKEN is missing!")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("add", add_album))
        logger.info("AOTY_O2S_BOT: Cloud Deployment Successful.")
        app.run_polling()
