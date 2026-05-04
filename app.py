import os
import sqlite3
import requests
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "tracker.db"

APP_SECRET = os.environ.get("APP_SECRET", "cambia-questa-password")
API_TOKEN = os.environ.get("TRACKER_API_TOKEN", "cambia-questo-token")
STARTING_BANKROLL = float(os.environ.get("STARTING_BANKROLL", "1000"))
CURRENCY = os.environ.get("CURRENCY", "EUR")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", APP_SECRET)


# 🔥 TELEGRAM FUNCTION
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=5
        )
    except:
        pass


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            symbol TEXT,
            side TEXT,
            entry REAL,
            exit REAL,
            amount REAL,
            pnl REAL,
            score REAL,
            status TEXT,
            source TEXT,
            notes TEXT
        )
        """)
        conn.commit()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_float(v, default=0.0):
    try:
        return float(str(v).replace(",", "."))
    except:
        return default


def require_login(f):
    @wraps(f)
    def wrapper(*a, **k):
        if session.get("logged_in"):
            return f(*a, **k)
        return redirect(url_for("login"))
    return wrapper


@app.before_request
def setup():
    init_db()


@app.route("/")
@require_login
def dashboard():
    with db() as conn:
        trades = [dict(x) for x in conn.execute("SELECT * FROM trades ORDER BY id DESC")]
    return render_template("dashboard.html", trades=trades)


# 🔥 BOT → CREA TRADE
@app.route("/api/trade", methods=["POST"])
def api_trade():
    data = request.get_json()
    if data.get("token") != API_TOKEN:
        return {"ok": False}, 401

    with db() as conn:
        cur = conn.execute("""
        INSERT INTO trades (created_at,symbol,side,entry,status,source)
        VALUES (?,?,?,?,?,?)
        """, (
            now_iso(),
            data.get("symbol"),
            data.get("side"),
            to_float(data.get("entry")),
            "open",
            "telegram"
        ))
        conn.commit()

    # 🔥 NOTIFICA APERTURA
    send_telegram(f"📡 NUOVO TRADE\n{data.get('symbol')} {data.get('side')}\nEntry: {data.get('entry')}")

    return {"ok": True}


# 🔥 CHIUSURA TRADE
@app.route("/close/<int:id>", methods=["POST"])
@require_login
def close_trade(id):
    exit_price = to_float(request.form.get("exit"))
    pnl = to_float(request.form.get("pnl"))

    with db() as conn:
        trade = conn.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()

        conn.execute("""
        UPDATE trades SET exit=?, pnl=?, status='closed' WHERE id=?
        """, (exit_price, pnl, id))
        conn.commit()

    # 🔥 NOTIFICA CHIUSURA
    send_telegram(
        f"💰 TRADE CHIUSO\n"
        f"{trade['symbol']} {trade['side']}\n"
        f"Entry: {trade['entry']}\n"
        f"Exit: {exit_price}\n"
        f"P/L: {pnl}€"
    )

    return redirect("/")


# 🔥 MANUALE
@app.route("/add", methods=["POST"])
@require_login
def add_manual():
    symbol = request.form.get("symbol")
    side = request.form.get("side")
    pnl = to_float(request.form.get("pnl"))

    with db() as conn:
        conn.execute("""
        INSERT INTO trades (created_at,symbol,side,pnl,status,source)
        VALUES (?,?,?,?,?,?)
        """, (now_iso(), symbol, side, pnl, "closed", "manual"))
        conn.commit()

    # 🔥 NOTIFICA MANUALE
    send_telegram(f"📊 TRADE MANUALE\n{symbol} {side}\nP/L: {pnl}€")

    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
@app.route("/test-telegram")
def test_telegram():
    send_telegram("🚀 TEST TELEGRAM OK")
    return "OK"
