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

# --- UNIVERSAL TRACK ID EXTRACTOR ---
def get_spotify_track_ids(url):
    try:
        # 1. Detect platform for logging
        is_itunes = "/i/" in url or "/us/i/" in url
        logger.info(f"Source Link: {'iTunes' if is_itunes else 'Spotify'}")

        # 2. Use Odesli to resolve the link to Spotify regardless of input
        api_url = f"https://api.song.link/v1-alpha.1/links?url={url}"
        r = requests.get(api_url).json()
        
        spotify_data = r.get('linksByPlatform', {}).get('spotify', {})
        spotify_url = spotify_data.get('url')
        
        if not spotify_url:
            logger.warning(f"Could not find a Spotify equivalent for: {url}")
            return []

        # Extract Spotify ID from the resolved URL
        spotify_id_match = re.search(r'spotify\.com/(?:album|track|s)/([a-zA-Z0-9]+)', spotify_url)
        if not spotify_id_match:
            spotify_id = spotify_data.get('entityUniqueId', '').split('::')[-1]
        else:
            spotify_id = spotify_id_match.group(1)

        # 3. Check if it's a single track or an album
        main_id = r.get('entityUniqueId')
        main_info = r.get('entitiesByUniqueId', {}).get(main_id, {})

        if main_info.get('type') == 'song':
            return [spotify_id]

        # 4. For Albums, use the Spotify ID to unpack the tracks
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

# --- MESSAGE HANDLER (CHANNEL & TOPIC COMPATIBLE) ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Fix: Get the correct message object (Private, Group Topic, or Channel)
    msg = update.channel_post or update.message
    
    if not msg or not msg.text:
        return

    # Fix: Reference msg.text instead of undefined 'text'
    url = next((w for w in msg.text.split() if "http" in w), None)
    
    if url and any(domain in url for domain in ["album.link", "odesli.co", "song.link"]):
        logger.info(f"📡 Processing link: {url}")
        
        track_ids = get_spotify_track_ids(url)
        if not track_ids:
            logger.warning("No track IDs found.")
            return

        logger.info(f"✅ Found {len(track_ids)} tracks. Adding to playlist...")

        for tid in track_ids:
            ifttt_url = f"https://maker.ifttt.com/trigger/{EVENT_NAME}/with/key/{IFTTT_KEY}"
            payload = {"value1": tid}
            
            try:
                response = requests.post(ifttt_url, json=payload)
                if response.status_code == 200:
                    logger.info(f"🚀 Sent to IFTTT: {tid}")
                else:
                    logger.error(f"❌ IFTTT Error: {response.status_code}")
            except Exception as e:
                logger.error(f"❌ Connection Error: {e}")
            
            # Preserve 'Date Added' order in Spotify
            time.sleep(2)

if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Listen to standard messages and channel posts
    message_filter = (filters.TEXT & (~filters.COMMAND)) | filters.ChatType.CHANNEL
    app.add_handler(MessageHandler(message_filter, handle_message))
    
    logger.info("Bot is active on Koyeb. Listening for Spotify/iTunes links...")
    app.run_polling()
