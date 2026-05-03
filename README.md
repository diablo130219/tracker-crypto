# Crypto Bankroll Tracker V3

Dashboard online per Render con:

- segnali automatici dal bot Telegram tramite `/api/trade`
- trade aperti visibili in dashboard
- chiusura manuale profit/loss per ogni trade aperto
- bankroll aggiornato solo sui trade chiusi
- storico completo
- grafico andamento bankroll
- endpoint `/healthz`

## Variabili Render

```txt
APP_SECRET=la_password_dashboard
TRACKER_API_TOKEN=token_segreto_api
STARTING_BANKROLL=1000
CURRENCY=EUR
```

## Build / Start

```txt
Build Command: pip install -r requirements.txt
Start Command: gunicorn app:app
```

## Bot Telegram

Nel servizio Render del bot aggiungi:

```txt
TRACKER_URL=https://tracker-crypto.onrender.com
TRACKER_API_TOKEN=lo_stesso_token_del_tracker
```

Quando il bot invia BUY o SELL, crea un trade aperto. Lo chiudi manualmente dalla dashboard inserendo P/L positivo o negativo.
