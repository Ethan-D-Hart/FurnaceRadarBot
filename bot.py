import os
import requests
import logging
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# --- 1. CONFIG ---
TOKEN = os.getenv("BOT_TOKEN")
IFTTT_KEY = os.getenv("IFTTT_KEY")
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
        # 1. Get Album/Artist names from Odesli
        api_url = f"https://api.song.link/v1-alpha.1/links?url={odesli_url}"
        r = requests.get(api_url).json()
        
        main_id = r.get('entityUniqueId')
        main_info = r.get('entitiesByUniqueId', {}).get(main_id, {})
        album_artist = main_info.get('artistName', '')
        album_title = main_info.get('title', '')

        # 2. STEP ONE: Find the Album ID
        search_url = "https://itunes.apple.com/search"
        search_params = {
            "term": f"{album_title} {album_artist}",
            "entity": "album", # We search for the ALBUM first, not songs
            "limit": 1
        }
        search_res = requests.get(search_url, params=search_params).json()
        
        if not search_res.get('results'):
            return []

        collection_id = search_res['results'][0].get('collectionId')

        # 3. STEP TWO: Lookup all tracks by that specific Collection ID
        # This is the 'Secret Sauce' that gets every single song on the disc
        lookup_url = f"https://itunes.apple.com/lookup?id={collection_id}&entity=song"
        lookup_res = requests.get(lookup_url).json()

        tracks = []
        for item in lookup_res.get('results', []):
            # The lookup returns the 'collection' (album) as the first item,
            # so we only grab the items that are actually 'track' types.
            if item.get('wrapperType') == 'track':
                tracks.append({
                    "title": item.get('trackName'),
                    "artist": item.get('artistName')
                })

        logger.info(f"✅ Deep Lookup found {len(tracks)} tracks for ID {collection_id}")
        return tracks

    except Exception as e:
        logger.error(f"❌ Lookup Error: {e}")
        return []

# --- 4. MESSAGE HANDLER (ALWAYS LISTENING) ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return
    
    url = next((w for w in text.split() if "http" in w), None)
    
    if url and any(domain in url for domain in ["album.link", "odesli.co", "song.link"]):
        # Use the more compatible way to react
        try:
            await context.bot.set_message_reaction(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                reaction=[{"type": "emoji", "emoji": "⚡"}]
            )
        except Exception as e:
            logger.warning(f"Could not add reaction: {e}")
        
        logger.info(f"📡 Link detected: {url}")
        tracks = get_tracks_from_entities(url)
        
        if not tracks:
            logger.warning("No tracks found.")
            return

        for track in tracks:
            ifttt_url = f"https://maker.ifttt.com/trigger/{EVENT_NAME}/with/key/{IFTTT_KEY}"
            try:
                requests.post(ifttt_url, json={"value1": track['title'], "value2": track['artist']})
                logger.info(f"✅ Added: {track['title']}")
            except: pass
            time.sleep(0.7)

# --- 5. MAIN STARTUP ---
if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start()

    if not TOKEN:
        logger.error("BOT_TOKEN environment variable is missing!")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        # Changed back to MessageHandler to listen to all text
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        logger.info("AOTY_O2S_BOT: Always-On Listener Active.")
        app.run_polling()
