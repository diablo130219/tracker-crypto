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
APP_BRAND = "CryptoNow"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", APP_SECRET)


def send_telegram_message(text):
    """Invia una notifica Telegram. Non blocca mai il tracker se Telegram fallisce."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        app.logger.warning("Telegram non configurato: mancano TELEGRAM_TOKEN o TELEGRAM_CHAT_ID")
        return False

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if not response.ok:
            app.logger.error("Errore Telegram %s: %s", response.status_code, response.text)
            return False
        return True
    except Exception as e:
        app.logger.error("Errore invio Telegram: %s", e)
        return False


def format_money(value):
    try:
        value = float(value or 0)
    except Exception:
        value = 0.0
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f} {CURRENCY}"


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                entry REAL,
                exit REAL,
                amount REAL DEFAULT 0,
                pnl REAL DEFAULT 0,
                score REAL,
                status TEXT DEFAULT 'open',
                source TEXT DEFAULT 'telegram',
                notes TEXT DEFAULT ''
            )
            """
        )
        conn.commit()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def require_login(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("logged_in"):
            return func(*args, **kwargs)
        return redirect(url_for("login"))
    return wrapper


def read_trades(limit=None):
    query = "SELECT * FROM trades ORDER BY datetime(created_at) DESC, id DESC"
    params = []
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    with db() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def calc_stats():
    trades = list(reversed(read_trades()))
    bankroll = STARTING_BANKROLL
    curve = [{"date": "start", "bankroll": round(bankroll, 2), "pnl": 0, "symbol": "START"}]
    wins = losses = 0
    pnl_total = 0.0
    open_count = 0
    closed_count = 0
    best = 0.0
    worst = 0.0

    for t in trades:
        status = str(t.get("status") or "").lower()
        pnl = float(t.get("pnl") or 0)
        if status == "open":
            open_count += 1
            continue

        if status == "closed":
            closed_count += 1
            pnl_total += pnl
            bankroll += pnl
            best = max(best, pnl)
            worst = min(worst, pnl)

            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1

            curve.append({
                "date": t["created_at"][:10],
                "bankroll": round(bankroll, 2),
                "pnl": round(pnl, 2),
                "symbol": t["symbol"],
            })

    closed_for_winrate = wins + losses

    return {
        "starting_bankroll": round(STARTING_BANKROLL, 2),
        "bankroll": round(bankroll, 2),
        "pnl_total": round(pnl_total, 2),
        "roi": round((pnl_total / STARTING_BANKROLL * 100), 2) if STARTING_BANKROLL else 0,
        "trades_count": len(trades),
        "open_count": open_count,
        "closed_count": closed_count,
        "wins": wins,
        "losses": losses,
        "best": round(best, 2),
        "worst": round(worst, 2),
        "winrate": round((wins / closed_for_winrate * 100), 1) if closed_for_winrate else 0,
        "currency": CURRENCY,
        "curve": curve,
    }


@app.before_request
def setup():
    init_db()


@app.route("/healthz")
def healthz():
    return "OK", 200


@app.route("/test-telegram")
def test_telegram():
    ok = send_telegram_message("🚀 <b>CryptoNow</b>\nTest Telegram OK ✅")
    return ("Telegram OK" if ok else "Telegram NON inviato: controlla TELEGRAM_TOKEN e TELEGRAM_CHAT_ID nei log Render"), 200


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == APP_SECRET:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        error = "Password errata"
    return render_template("login.html", error=error, brand=APP_BRAND)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@require_login
def dashboard():
    trades = read_trades(180)
    open_trades = [t for t in trades if str(t.get("status") or "").lower() == "open"]
    closed_trades = [t for t in trades if str(t.get("status") or "").lower() == "closed"]
    return render_template(
        "dashboard.html",
        stats=calc_stats(),
        trades=trades,
        open_trades=open_trades,
        closed_trades=closed_trades,
        brand=APP_BRAND,
    )


@app.route("/api/stats")
def api_stats():
    return jsonify(calc_stats())


@app.route("/api/trade", methods=["POST"])
def api_trade():
    data = request.get_json(silent=True) or {}
    token = data.get("token") or request.headers.get("X-Tracker-Token")

    if token != API_TOKEN:
        return jsonify({"ok": False, "error": "token non valido"}), 401

    symbol = str(data.get("symbol") or data.get("pair") or "UNKNOWN").upper()
    side = str(data.get("side") or data.get("signal") or "").upper()

    if side not in {"BUY", "SELL", "LONG", "SHORT", "MANUAL"}:
        side = "SIGNAL"

    values = {
        "created_at": data.get("created_at") or now_iso(),
        "symbol": symbol,
        "side": side,
        "entry": to_float(data.get("entry") or data.get("price")),
        "exit": to_float(data.get("exit")),
        "amount": to_float(data.get("amount")),
        "pnl": to_float(data.get("pnl") or data.get("profit")),
        "score": to_float(data.get("score")),
        "status": str(data.get("status") or "open").lower(),
        "source": str(data.get("source") or "telegram"),
        "notes": str(data.get("notes") or ""),
    }

    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO trades (created_at, symbol, side, entry, exit, amount, pnl, score, status, source, notes)
            VALUES (:created_at, :symbol, :side, :entry, :exit, :amount, :pnl, :score, :status, :source, :notes)
            """,
            values,
        )
        conn.commit()

    if values["status"] == "open":
        send_telegram_message(
            f"📡 <b>NUOVO SEGNALE APERTO</b>\n"
            f"🪙 <b>{values['symbol']}</b>\n"
            f"📈 Side: <b>{values['side']}</b>\n"
            f"💵 Entrata: <b>{values['entry']}</b>\n"
            f"📊 Score: <b>{values['score']}</b>\n"
            f"🔗 Fonte: {values['source']}"
        )
    elif values["status"] == "closed":
        pnl = values["pnl"]
        emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
        send_telegram_message(
            f"{emoji} <b>TRADE INSERITO GIÀ CHIUSO</b>\n"
            f"🪙 <b>{values['symbol']}</b> {values['side']}\n"
            f"💵 Entrata: <b>{values['entry']}</b>\n"
            f"🏁 Uscita: <b>{values['exit']}</b>\n"
            f"💰 P/L: <b>{format_money(pnl)}</b>"
        )

    return jsonify({"ok": True, "id": cur.lastrowid, "stats": calc_stats()})


@app.route("/add", methods=["POST"])
@require_login
def add_manual():
    values = {
        "created_at": request.form.get("created_at") or now_iso(),
        "symbol": (request.form.get("symbol") or "MANUAL").upper(),
        "side": (request.form.get("side") or "MANUAL").upper(),
        "entry": to_float(request.form.get("entry")),
        "exit": to_float(request.form.get("exit")),
        "amount": to_float(request.form.get("amount")),
        "pnl": to_float(request.form.get("pnl")),
        "score": to_float(request.form.get("score")),
        "status": request.form.get("status") or "closed",
        "source": "manual",
        "notes": request.form.get("notes") or "",
    }

    with db() as conn:
        conn.execute(
            """
            INSERT INTO trades (created_at, symbol, side, entry, exit, amount, pnl, score, status, source, notes)
            VALUES (:created_at, :symbol, :side, :entry, :exit, :amount, :pnl, :score, :status, :source, :notes)
            """,
            values,
        )
        conn.commit()

    status = str(values["status"]).lower()
    if status == "closed":
        pnl = values["pnl"]
        emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
        send_telegram_message(
            f"{emoji} <b>OPERAZIONE MANUALE CHIUSA</b>\n"
            f"🪙 <b>{values['symbol']}</b> {values['side']}\n"
            f"💵 Entrata: <b>{values['entry']}</b>\n"
            f"🏁 Uscita: <b>{values['exit']}</b>\n"
            f"💰 P/L: <b>{format_money(pnl)}</b>\n"
            f"📝 Note: {values['notes'] or '-'}"
        )
    else:
        send_telegram_message(
            f"📌 <b>OPERAZIONE MANUALE APERTA</b>\n"
            f"🪙 <b>{values['symbol']}</b> {values['side']}\n"
            f"💵 Entrata: <b>{values['entry']}</b>"
        )

    return redirect(url_for("dashboard"))


@app.route("/close/<int:trade_id>", methods=["POST"])
@require_login
def close_trade(trade_id):
    exit_price = to_float(request.form.get("exit"))
    pnl = to_float(request.form.get("pnl"))
    notes_extra = request.form.get("notes") or ""

    with db() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not row:
            return redirect(url_for("dashboard"))

        trade = dict(row)
        old_notes = trade.get("notes") or ""
        notes = old_notes

        if notes_extra:
            notes = (old_notes + " | " if old_notes else "") + notes_extra

        conn.execute(
            "UPDATE trades SET exit = ?, pnl = ?, status = 'closed', notes = ? WHERE id = ?",
            (exit_price, pnl, notes, trade_id),
        )
        conn.commit()

    emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
    result_text = "PROFIT" if pnl > 0 else "LOSS" if pnl < 0 else "PAREGGIO"

    send_telegram_message(
        f"{emoji} <b>TRADE CHIUSO - {result_text}</b>\n"
        f"🪙 <b>{trade['symbol']}</b> {trade['side']}\n"
        f"💵 Entrata: <b>{trade.get('entry') or 0}</b>\n"
        f"🏁 Uscita: <b>{exit_price}</b>\n"
        f"💰 P/L: <b>{format_money(pnl)}</b>\n"
        f"📊 Score: <b>{trade.get('score') or 0}</b>\n"
        f"📝 Note: {notes or '-'}"
    )

    return redirect(url_for("dashboard"))


@app.route("/delete/<int:trade_id>", methods=["POST"])
@require_login
def delete_trade(trade_id):
    with db() as conn:
        conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
        conn.commit()
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
