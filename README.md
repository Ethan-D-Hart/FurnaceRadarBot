# AOTY_O2S_BOT

A technical middleware service that automates the transition from music discovery on Telegram to playlist curation on Spotify. This bot intercepts **Odesli (Songlink/Albumlink)** URLs, resolves platform-agnostic metadata, and serializes track insertion via IFTTT.

## ⚙️ Technical Architecture

The bot functions as a stateless bridge, employing the following logic flow:

1. **Ingestion**: Monitors `channel_post` and `message` updates via the `python-telegram-bot` library.
2. **Platform Inference**: Detects URL structures for Spotify (`/s/`) or Apple Music (`/i/`).
3. **Entity Resolution**: Queries the Odesli API (`v1-alpha.1/links`) to map input URLs to a canonical Spotify `entityUniqueId`, resolving numeric iTunes IDs to Spotify Base62 IDs.
4. **Metadata Expansion**: For album entities, the service scrapes the Spotify Embed JSON blob (`__NEXT_DATA__`) to bypass standard API tracklist truncation, ensuring 100% capture of large (25+) tracklists.
5. **Serialization**: Forwards Track IDs to IFTTT Webhooks with a 2000ms `time.sleep` interval to prevent race conditions and preserve the original album's chronological "Date Added" order.

## 🛠 Configuration

### Environment Variables

The following variables must be configured in your deployment environment:

| Variable | Description |
| --- | --- |
| `BOT_TOKEN` | Telegram Bot API token provided by `@BotFather`. |
| `IFTTT_KEY` | Unique Webhook key from your IFTTT Maker service. |
| `PORT` | The internal port for the HTTP health check (default: `8000`). |

### IFTTT Applet Setup

To handle the automated addition, configure an IFTTT Applet as follows:

* **Trigger**: Webhooks (`Receive a web request`)
* **Event Name**: `add_spotify_song`


* **Action**: Spotify (`Add track to a playlist`)
* **Search Query**: `{{Value1}}`


* **Applet URL**: [Insert Link Here]

## 🖥 Deployment

### Health Check & Uptime

The bot includes a lightweight `HTTPServer` running on a background thread. This is designed for cloud providers (like Koyeb) to perform GET requests against the `/` route to verify container health.

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/aoty_o2s_bot.git

# Install dependencies
pip install python-telegram-bot requests

# Run the service
python bot.py

```

## 💾 Core Logic: Platform Resolution

The service ensures that numeric Apple Music IDs are converted to Spotify-readable formats before being sent to the IFTTT pipeline.

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
