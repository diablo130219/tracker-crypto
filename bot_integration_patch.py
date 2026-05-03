# PEZZO DA AGGIUNGERE AL TUO bot.py
# 1) aggiungi: import requests
# 2) aggiungi le due variabili sotto TELEGRAM_CHAT_ID
# 3) aggiungi la funzione send_to_tracker
# 4) richiama send_to_tracker(symbol, result) dopo l'invio del messaggio Telegram

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
                "signal": result.get("signal"),
                "price": result.get("price"),
                "score": result.get("score"),
                "status": "signal",
                "source": "telegram",
                "notes": "Segnale automatico dal bot Telegram"
            },
            timeout=10
        )
    except Exception as e:
        logger.warning(f"Tracker non raggiungibile: {e}")
