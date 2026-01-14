import os, requests, logging, time, threading, re, json
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN")
IFTTT_KEY = os.getenv("IFTTT_KEY")
EVENT_NAME = "add_spotify_song"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("AOTY_O2S")

# --- KOYEB HEALTH SERVER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive!")
    def log_message(self, format, *args): return

def run_health_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# --- TRACK ID EXTRACTOR (MAINTAINS ORDER) ---
def get_spotify_track_ids(url):
    try:
        # Extract Spotify ID from URL
        spotify_id_match = re.search(r'/s/([a-zA-Z0-9]+)', url)
        if not spotify_id_match: return []
        spotify_id = spotify_id_match.group(1)

        # Use Odesli to check if it's a single track
        api_url = f"https://api.song.link/v1-alpha.1/links?url={url}"
        r = requests.get(api_url).json()
        main_id = r.get('entityUniqueId')
        main_info = r.get('entitiesByUniqueId', {}).get(main_id, {})

        if main_info.get('type') == 'song':
            return [spotify_id]

        # If it's an album, unpack all Track IDs via Spotify Embed
        embed_url = f"https://open.spotify.com/embed/album/{spotify_id}"
        response = requests.get(embed_url, headers={'User-Agent': 'Mozilla/5.0'})
        pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
        match = re.search(pattern, response.text)
        
        if match:
            data = json.loads(match.group(1))
            album_data = data['props']['pageProps']['state']['data']['entity']
            # trackList is ordered 1-N. We map them into a list to preserve that index.
            track_ids = [t['uri'].split(':')[-1] for t in album_data.get('trackList', [])]
            return track_ids
            
        return []
    except Exception as e:
        logger.error(f"Error fetching IDs: {e}")
        return []

# --- MESSAGE HANDLER ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return
    
    url = next((w for w in text.split() if "http" in w), None)
    
    if url and any(domain in url for domain in ["album.link", "odesli.co", "song.link"]):
        logger.info(f"📡 Link detected: {url}")
        
        track_ids = get_spotify_track_ids(url)
        if not track_ids:
            logger.warning("No track IDs found for this link.")
            return

        logger.info(f"✅ Found {len(track_ids)} tracks. Adding in order...")

        for tid in track_ids:
            ifttt_url = f"https://maker.ifttt.com/trigger/{EVENT_NAME}/with/key/{IFTTT_KEY}"
            payload = {"value1": tid}
            
            try:
                response = requests.post(ifttt_url, json=payload)
                if response.status_code == 200:
                    logger.info(f"🚀 Sent to IFTTT: {tid}")
                else:
                    logger.error(f"❌ IFTTT Error ({response.status_code}): {response.text}")
            except Exception as e:
                logger.error(f"❌ Connection Error: {e}")
            
            # CRITICAL: 2-second sleep ensures Spotify processes the add
            # before the next webhook arrives, preserving the 'Date Added' order.
            time.sleep(2)

if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    logger.info("Bot is active on Koyeb...")
    app.run_polling()
