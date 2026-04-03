# AOTY_O2S_BOT

A technical middleware service that automates the transition from music discovery on Telegram to playlist curation on Spotify. The bot scans Telegram messages for Spotify links, ignores Apple Music links, and serializes track insertion via IFTTT.

## ⚙️ Technical Architecture

The bot functions as a stateless bridge, employing the following logic flow:

1. **Ingestion**: Monitors `channel_post` and `message` updates via the `python-telegram-bot` library.
2. **URL Selection**: Extracts all URLs from the message and uses the **first** supported Spotify URL in message order (`open.spotify.com/track/...` or `open.spotify.com/album/...`).
3. **Apple Ignore Rule**: Apple Music links may be present in the same message but are ignored.
4. **Metadata Expansion**: For album entities, the service scrapes the Spotify Embed JSON blob (`__NEXT_DATA__`) to capture all track IDs from the album tracklist.
5. **Serialization**: Forwards track IDs to IFTTT Webhooks with a 2000ms `time.sleep` interval to preserve insertion order.

## 🛠 Configuration

### Environment Variables

The following variables must be configured in your deployment environment:

| Variable | Description |
| --- | --- |
| `BOT_TOKEN` | Telegram Bot API token provided by `@BotFather`. |
| `IFTTT_KEY` | Unique Webhook key from your IFTTT Maker service. |

### IFTTT Applet Setup

To handle the automated addition, configure an IFTTT Applet as follows:

* **Trigger**: Webhooks (`Receive a web request`)
* **Event Name**: `add_spotify_song`


* **Action**: Spotify (`Add track to a playlist`)
* **Search Query**: `{{Value1}}`


* **Applet URL**: [Insert Link Here]

## 🖥 Deployment

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/aoty_o2s_bot.git

# Install dependencies
pip install -r requirements.txt

# Run the service
python bot.py

```

## 💾 Core Logic: Spotify URL Extraction

The service reads raw message text, picks the first supported Spotify URL, and extracts the Spotify entity ID (`track` or `album`) before sending IDs through the IFTTT pipeline.

```python
# Resolution logic for iTunes to Spotify mapping
spotify_id_match = re.search(r'spotify\.com/(?:album|track|s)/([a-zA-Z0-9]+)', spotify_url)
if not spotify_id_match:
    # Fallback to internal Odesli unique mapping for non-standard URLs
    spotify_id = spotify_data.get('entityUniqueId', '').split('::')[-1]

```

## 🔗 Links

* **Cloud Dashboard**: [Insert Link Here]
* **IFTTT Configuration**: [Insert Link Here]

---

**Next Step**: Would you like me to generate a `requirements.txt` file for you to include in your repository so Koyeb knows exactly which libraries to install?
