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

APP_SECRET = os.environ.get("APP_SECRET", "admin")
API_TOKEN = os.environ.get("TRACKER_API_TOKEN", "")
STARTING_BANKROLL = float(os.environ.get("STARTING_BANKROLL", "100"))
CURRENCY = os.environ.get("CURRENCY", "EUR")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

app = Flask(__name__)
app.secret_key = APP_SECRET


# ---------------- TELEGRAM ----------------
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram non configurato")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=5
        )
        print("Telegram status:", r.status_code)
    except Exception as e:
        print("Errore Telegram:", e)


# ---------------- DB ----------------
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
            pnl REAL,
            status TEXT,
            source TEXT
        )
        """)
        conn.commit()


def now():
    return datetime.now(timezone.utc).isoformat()


# ---------------- LOGIN ----------------
def require_login(f):
    @wraps(f)
    def wrapper(*a, **k):
        if session.get("logged"):
            return f(*a, **k)
        return redirect("/login")
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == APP_SECRET:
            session["logged"] = True
            return redirect("/")
    return """
    <form method="post">
        <input name="password" placeholder="Password"/>
        <button>Login</button>
    </form>
    """


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- HOME ----------------
@app.route("/")
@require_login
def home():
    with db() as conn:
        trades = conn.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
    return render_template("dashboard.html", trades=trades)


# ---------------- TEST TELEGRAM ----------------
@app.route("/test-telegram")
def test_telegram():
    send_telegram("🚀 TEST OK CryptoNow")
    return "OK"


# ---------------- API BOT ----------------
@app.route("/api/trade", methods=["POST"])
def api_trade():
    data = request.json
    if data.get("token") != API_TOKEN:
        return {"ok": False}, 401

    with db() as conn:
        conn.execute("""
        INSERT INTO trades (created_at, symbol, side, entry, status, source)
        VALUES (?,?,?,?,?,?)
        """, (now(), data["symbol"], data["side"], data["entry"], "open", "bot"))
        conn.commit()

    send_telegram(f"📡 TRADE APERTO\n{data['symbol']} {data['side']}\nEntry: {data['entry']}")
    return {"ok": True}


# ---------------- CHIUDI TRADE ----------------
@app.route("/close/<int:id>", methods=["POST"])
@require_login
def close_trade(id):
    exit_price = float(request.form.get("exit", 0))
    pnl = float(request.form.get("pnl", 0))

    with db() as conn:
        trade = conn.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()

        conn.execute("""
        UPDATE trades SET exit=?, pnl=?, status='closed' WHERE id=?
        """, (exit_price, pnl, id))
        conn.commit()

    send_telegram(
        f"💰 TRADE CHIUSO\n"
        f"{trade['symbol']} {trade['side']}\n"
        f"Entry: {trade['entry']}\n"
        f"Exit: {exit_price}\n"
        f"P/L: {pnl}€"
    )

    return redirect("/")


# ---------------- MANUALE ----------------
@app.route("/add", methods=["POST"])
@require_login
def add_manual():
    symbol = request.form.get("symbol")
    side = request.form.get("side")
    pnl = float(request.form.get("pnl", 0))

    with db() as conn:
        conn.execute("""
        INSERT INTO trades (created_at,symbol,side,pnl,status,source)
        VALUES (?,?,?,?,?,?)
        """, (now(), symbol, side, pnl, "closed", "manual"))
        conn.commit()

    send_telegram(f"📊 TRADE MANUALE\n{symbol} {side}\nP/L: {pnl}€")

    return redirect("/")


# ---------------- START ----------------
init_db()
