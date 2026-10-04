"""Run from the project root: python scripts/get_chat_id.py."""
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


def main() -> int:
    print("First open your bot in Telegram, press Start, and send it a message.")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("Set TELEGRAM_BOT_TOKEN in .env or your environment first.")
        return 1
    try:
        response = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=(10, 30))
        if response.status_code in (401, 404):
            print("Telegram rejected the token (HTTP 401/404). Save the new BotFather token in .env.")
            print("If PowerShell has an older TELEGRAM_BOT_TOKEN environment variable, remove it before retrying.")
            return 1
        if response.status_code == 409:
            print("Telegram reports a conflict (HTTP 409): this bot has an active webhook or another getUpdates consumer.")
            print("Stop other bot integrations/pollers, or remove its webhook if you no longer need that integration.")
            return 1
        if response.status_code != 200:
            print(f"Telegram returned HTTP {response.status_code}. Try again later; no token was printed.")
            return 1
        data = response.json()
        if data.get("ok") is not True:
            raise ValueError
        chats = set()
        for update in data["result"]:
            for key in ("message", "edited_message", "channel_post", "my_chat_member"):
                chat = update.get(key, {}).get("chat", {})
                if "id" in chat:
                    chats.add(chat["id"])
        for chat_id in sorted(chats):
            print(f"TELEGRAM_CHAT_ID={chat_id}")
        if not chats:
            print("No chats yet. Send a fresh message to the bot and run this script again.")
        return 0
    except requests.exceptions.SSLError:
        print("TLS certificate verification failed connecting to Telegram. Check your network/proxy certificate setup; do not disable verification.")
        return 1
    except requests.Timeout:
        print("Connection to Telegram timed out. Check whether api.telegram.org is reachable on your network.")
        return 1
    except requests.ConnectionError:
        print("Cannot connect to api.telegram.org. Check your internet connection, DNS, firewall, or proxy.")
        return 1
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        print("Telegram request or response was invalid. Try again; raw responses are hidden to protect your token.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
