# PATCH BOT TELEGRAM -> TRACKER
# Aggiungi questo al tuo bot.py.
# Poi chiama send_to_tracker(symbol, result) subito dopo send_message(...)
# nel punto in cui il bot manda il segnale Telegram.

import os
import requests

TRACKER_URL = os.environ.get("TRACKER_URL", "")
TRACKER_API_TOKEN = os.environ.get("TRACKER_API_TOKEN", "")

def send_to_tracker(symbol, result):
    if not TRACKER_URL or not TRACKER_API_TOKEN:
        return
    try:
        requests.post(
            f"{TRACKER_URL.rstrip('/')}/api/trade",
            json={
                "token": TRACKER_API_TOKEN,
                "symbol": symbol,
                "signal": result.get("signal") or result.get("side"),
                "price": result.get("price") or result.get("entry"),
                "score": result.get("score"),
                "status": "open",
                "source": "telegram",
                "notes": "Segnale automatico dal bot Telegram"
            },
            timeout=10
        )
    except Exception as e:
        print(f"Tracker non raggiungibile: {e}")
