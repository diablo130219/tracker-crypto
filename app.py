import os
import sqlite3
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

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", APP_SECRET)


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
                status TEXT DEFAULT 'signal',
                source TEXT DEFAULT 'telegram',
                notes TEXT DEFAULT ''
            )
            """
        )
        conn.commit()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    curve = []
    wins = losses = 0
    pnl_total = 0.0

    for t in trades:
        pnl = float(t.get("pnl") or 0)
        pnl_total += pnl
        bankroll += pnl
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

    closed = wins + losses
    return {
        "starting_bankroll": round(STARTING_BANKROLL, 2),
        "bankroll": round(bankroll, 2),
        "pnl_total": round(pnl_total, 2),
        "roi": round((pnl_total / STARTING_BANKROLL * 100), 2) if STARTING_BANKROLL else 0,
        "trades_count": len(trades),
        "wins": wins,
        "losses": losses,
        "winrate": round((wins / closed * 100), 1) if closed else 0,
        "currency": CURRENCY,
        "curve": curve,
    }


@app.before_request
def setup():
    init_db()


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == APP_SECRET:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        error = "Password errata"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@require_login
def dashboard():
    return render_template("dashboard.html", stats=calc_stats(), trades=read_trades(80))


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
        "entry": float(data.get("entry") or data.get("price") or 0),
        "exit": float(data.get("exit") or 0),
        "amount": float(data.get("amount") or 0),
        "pnl": float(data.get("pnl") or data.get("profit") or 0),
        "score": float(data.get("score") or 0),
        "status": str(data.get("status") or "signal"),
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
    return jsonify({"ok": True, "id": cur.lastrowid, "stats": calc_stats()})


@app.route("/add", methods=["POST"])
@require_login
def add_manual():
    values = {
        "created_at": request.form.get("created_at") or now_iso(),
        "symbol": (request.form.get("symbol") or "MANUAL").upper(),
        "side": (request.form.get("side") or "MANUAL").upper(),
        "entry": float(request.form.get("entry") or 0),
        "exit": float(request.form.get("exit") or 0),
        "amount": float(request.form.get("amount") or 0),
        "pnl": float(request.form.get("pnl") or 0),
        "score": float(request.form.get("score") or 0),
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
