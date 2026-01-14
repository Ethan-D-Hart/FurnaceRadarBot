import requests
import logging
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("AOTY_O2S")

# --- CONFIG ---
TOKEN = "8542325435:AAHCPZQg5j0EmGx7W9N6KpIYmNcdtH83p70"
IFTTT_KEY = "tx1qmZkEiRz4WQ_T7o3oL"
EVENT_NAME = "add_spotify_song"

def get_tracks_from_entities(odesli_url):
    """Universal Entity Unpacking"""
    try:
        api_url = f"https://api.song.link/v1-alpha.1/links?url={odesli_url}"
        r = requests.get(api_url).json()
        
        main_entity_id = r.get('entityUniqueId')
        main_info = r.get('entitiesByUniqueId', {}).get(main_entity_id, {})
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
            # Fallback to iTunes Search
            it_res = requests.get(f"https://itunes.apple.com/search?term={album_title} {album_artist}&entity=song&limit=40").json()
            for item in it_res.get('results', []):
                if album_title in item.get('collectionName', '').lower() and item.get('trackName').lower() not in seen_titles:
                    tracks.append({"title": item.get('trackName'), "artist": item.get('artistName')})
                    seen_titles.add(item.get('trackName').lower())
        return tracks
    except: return []

def render_progress_bar(current, total):
    """Generates a visual [███░░] bar"""
    size = 10
    filled = int(size * current / total)
    bar = "█" * filled + "░" * (size - filled)
    percent = int((current / total) * 100)
    return f"`{bar}` {percent}% ({current}/{total})"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    url = next((w for w in text.split() if "http" in w), None)
    
    if url and any(domain in url for domain in ["album.link", "odesli.co", "song.link"]):
        status_msg = await update.message.reply_text("📡 Analyzing Album...")
        
        tracks = get_tracks_from_entities(url)
        
        if not tracks:
            await status_msg.edit_text("❌ No tracks found.")
            return

        total = len(tracks)
        await status_msg.edit_text(f"🚀 Found {total} tracks. Adding to Spotify...\n{render_progress_bar(0, total)}")
        
        success = 0
        for i, track in enumerate(tracks):
            ifttt_url = f"https://maker.ifttt.com/trigger/{EVENT_NAME}/with/key/{IFTTT_KEY}"
            try:
                res = requests.post(ifttt_url, json={"value1": track['title'], "value2": track['artist']})
                if res.status_code == 200:
                    success += 1
            except: pass

            # Update the loading bar every 1-2 tracks to avoid Telegram rate limits
            if (i + 1) % 1 == 0 or (i + 1) == total:
                progress_text = (
                    f"📦 **Adding tracks to Spotify...**\n"
                    f"Current: _{track['title']}_\n\n"
                    f"{render_progress_bar(i + 1, total)}"
                )
                try:
                    await status_msg.edit_text(progress_text, parse_mode="Markdown")
                except: pass # Ignore 'message not modified' errors

            time.sleep(0.7) # Safety delay for IFTTT and Telegram

        await update.message.reply_text(f"✅ **Mission Complete**\nAdded {success} tracks to your playlist.", parse_mode="Markdown")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    logger.info("AOTY_O2S_BOT with Progress Bar is Live.")
    app.run_polling()
