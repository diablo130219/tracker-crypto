# Crypto Bankroll Tracker

Tracker online leggero per Render, separato dal bot Telegram.

## Variabili ambiente Render

Imposta queste variabili:

- `APP_SECRET` = password per accedere alla dashboard
- `TRACKER_API_TOKEN` = token segreto usato dal bot Telegram per inviare dati
- `STARTING_BANKROLL` = capitale iniziale, esempio `1000`
- `CURRENCY` = valuta, esempio `EUR`

## Deploy Render

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
gunicorn app:app
```

## Collegamento al bot Telegram

Nel tuo `bot.py`, aggiungi questo import in alto:

```python
import requests
```

Aggiungi queste variabili sotto quelle Telegram:

```python
TRACKER_URL = os.environ.get("TRACKER_URL", "")
TRACKER_API_TOKEN = os.environ.get("TRACKER_API_TOKEN", "")
```

Aggiungi questa funzione:

```python
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
```

Poi, subito dopo questa riga nel ciclo:

```python
await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN_V2)
```

aggiungi:

```python
send_to_tracker(symbol, result)
```

## Variabili da aggiungere al bot Telegram

Nel servizio Render del bot Telegram aggiungi:

- `TRACKER_URL` = URL del tracker, esempio `https://crypto-bankroll-tracker.onrender.com`
- `TRACKER_API_TOKEN` = lo stesso token usato nel tracker

