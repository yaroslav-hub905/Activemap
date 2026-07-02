"""
ActivityMap Mini App — FastAPI Backend
Деплой: Railway (тот же проект что и бот, или отдельный)
"""
import hashlib, hmac, json, os, time, requests as req_lib
from urllib.parse import unquote
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import database as db

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TG_API    = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = FastAPI(title="ActivityMap API", docs_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Serve frontend ────────────────────────────────────────────
@app.get("/")
def serve_index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))

# ── Telegram initData validation ──────────────────────────────
def validate_init_data(init_data: str) -> dict:
    """Проверяет подпись Telegram WebApp initData (HMAC-SHA256)."""
    if not BOT_TOKEN or not init_data:
        raise HTTPException(401, "Missing auth")
    # URL-decode, then split key=value pairs
    params = {}
    for part in init_data.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            params[unquote(k)] = unquote(v)
    received_hash = params.pop("hash", "")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret  = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        raise HTTPException(401, "Invalid signature")
    try:
        return json.loads(params.get("user", "{}"))
    except Exception:
        raise HTTPException(401, "Bad user data")

def get_tg_user(x_init_data: str = Header(None)):
    if not x_init_data:
        raise HTTPException(401, "No init data")
    return validate_init_data(x_init_data)

# ── Telegram push helper ──────────────────────────────────────
def send_tg_message(chat_id: int, text: str):
    """Отправляет push через бота. Ошибки не блокируют основной запрос."""
    if not BOT_TOKEN or not chat_id:
        return
    try:
        req_lib.post(
            f"{TG_API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=4
        )
    except Exception:
        pass

# ── Category maps ─────────────────────────────────────────────
EMOJIS = {'coffee':'☕','walk':'🚶','bar':'🍺','sport':'⚽',
          'language':'💬','culture':'🎭','food':'🍜','work':'💻','other':'✨'}
LABELS = {'coffee':'Кофе / Чай','walk':'Прогулка','bar':'Бар / Вечер','sport':'Спорт',
          'language':'Языки','culture':'Культура','food':'Еда','work':'Коворкинг','other':'Другое'}

# ── Models ────────────────────────────────────────────────────
class RegisterBody(BaseModel):
    name: str
    age: int
    city: str
    init_data: str

class PinBody(BaseModel):
    category: str
    description: Optional[str] = ""
    time_text: str
    city: str

class InterestBody(BaseModel):
    activity_id: int

# ── Auth / Register ───────────────────────────────────────────
@app.post("/api/auth")
def auth(body: RegisterBody):
    tg_user  = validate_init_data(body.init_data)
    tg_id    = tg_user["id"]
    username = tg_user.get("username", "")
    name     = body.name.strip()[:30]
    age      = max(18, min(80, body.age))
    city     = body.city.strip()[:50]
    if not name or not city:
        raise HTTPException(400, "name and city required")
    db.upsert_user(tg_id, username, name, age, city)
    return {"ok": True, "user": {"tg_id": tg_id, "name": name, "age": age, "city": city}}

@app.get("/api/me")
def get_me(request: Request, x_init_data: str = Header(None)):
    tg_user = get_tg_user(x_init_data)
    with db.get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_user["id"],)).fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    user     = dict(row)
    activity = db.get_active_activity(user["tg_id"])
    return {"user": user, "myPin": activity}

# ── Pins ──────────────────────────────────────────────────────
@app.get("/api/pins")
def get_pins(city: str, x_init_data: str = Header(None)):
    tg_user = get_tg_user(x_init_data)
    with db.get_db() as conn:
        me = conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_user["id"],)).fetchone()
    activities = db.get_activities_in_city(city)
    result = []
    for a in activities:
        cat = a.get("category", "other")
        result.append({
            **dict(a),
            "emoji":    EMOJIS.get(cat, "✨"),
            "catLabel": LABELS.get(cat, "Другое"),
            "isMine":   bool(me and a["user_id"] == me["tg_id"])
        })
    return {"pins": result}

@app.post("/api/pins")
def create_pin(body: PinBody, x_init_data: str = Header(None)):
    tg_user = get_tg_user(x_init_data)
    with db.get_db() as conn:
        me = conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_user["id"],)).fetchone()
    if not me:
        raise HTTPException(404, "Register first")
    act_id = db.create_activity(me["tg_id"], body.category, body.description, body.time_text, body.city)
    return {"ok": True, "id": act_id}

@app.delete("/api/pins/mine")
def delete_my_pin(x_init_data: str = Header(None)):
    tg_user = get_tg_user(x_init_data)
    with db.get_db() as conn:
        me = conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_user["id"],)).fetchone()
    if not me:
        raise HTTPException(404, "User not found")
    activity = db.get_active_activity(me["tg_id"])
    if not activity:
        raise HTTPException(404, "No active pin")
    db.deactivate_activity(activity["id"], me["tg_id"])
    return {"ok": True}

# ── Interest + push notification ──────────────────────────────
@app.post("/api/interest")
def express_interest(body: InterestBody, x_init_data: str = Header(None)):
    tg_user = get_tg_user(x_init_data)
    with db.get_db() as conn:
        me = conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_user["id"],)).fetchone()
    if not me:
        raise HTTPException(404, "Register first")
    try:
        db.add_interest(body.activity_id, me["tg_id"])
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(409, "Already interested")
        raise HTTPException(500, str(e))

    # Notify pin owner
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT a.*, u.tg_id AS owner_tg_id, a.description "
            "FROM activities a JOIN users u ON a.user_id=u.tg_id WHERE a.id=?",
            (body.activity_id,)
        ).fetchone()
    if row and row["owner_tg_id"] and row["owner_tg_id"] != tg_user["id"]:
        cat   = row.get("category", "other")
        emoji = EMOJIS.get(cat, "✨")
        label = LABELS.get(cat, "Другое")
        desc  = row.get("description") or ""
        msg = (
            f"👋 <b>{me['name']}</b> ({me['city']}) хочет присоединиться к твоей активности!\n\n"
            f"{emoji} <b>{label}</b>" + (f" · {desc}" if desc else "") +
            "\n\nОткрой ActivityMap → Заявки, чтобы принять или отклонить."
        )
        send_tg_message(row["owner_tg_id"], msg)

    return {"ok": True}

# ── Requests (accept / decline) ───────────────────────────────
@app.get("/api/requests")
def get_requests(x_init_data: str = Header(None)):
    tg_user = get_tg_user(x_init_data)
    data = db.get_requests_for_user(tg_user["id"])

    # Enrich with emoji/label so frontend doesn't need to
    for r in data["received"]:
        cat = r.get("category", "other")
        r["emoji"] = EMOJIS.get(cat, "✨")
        r["catLabel"] = LABELS.get(cat, "Другое")
    for r in data["sent"]:
        cat = r.get("category", "other")
        r["emoji"] = EMOJIS.get(cat, "✨")
        r["catLabel"] = LABELS.get(cat, "Другое")

    return data


@app.post("/api/requests/{interest_id}/accept")
def accept_request(interest_id: int, x_init_data: str = Header(None)):
    tg_user = get_tg_user(x_init_data)
    with db.get_db() as conn:
        me = conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_user["id"],)).fetchone()
    if not me:
        raise HTTPException(404, "User not found")

    ok = db.update_interest_status(interest_id, me["tg_id"], "accepted")
    if not ok:
        raise HTTPException(404, "Interest not found or not yours")

    # Notify the person who expressed interest
    with db.get_db() as conn:
        row = conn.execute("""
            SELECT i.from_user, u.name AS requester_name,
                   a.category, a.description
            FROM interests i
            JOIN users u ON u.tg_id = i.from_user
            JOIN activities a ON a.id = i.activity_id
            WHERE i.id = ?
        """, (interest_id,)).fetchone()

    if row:
        cat   = row["category"] or "other"
        emoji = EMOJIS.get(cat, "✨")
        label = LABELS.get(cat, "Другое")
        msg = (
            f"✅ <b>{me['name']}</b> принял твою заявку!\n\n"
            f"{emoji} <b>{label}</b>\n\n"
            f"Открой ActivityMap → Мэтчи, чтобы написать им."
        )
        send_tg_message(row["from_user"], msg)

    return {"ok": True}


@app.post("/api/requests/{interest_id}/decline")
def decline_request(interest_id: int, x_init_data: str = Header(None)):
    tg_user = get_tg_user(x_init_data)
    with db.get_db() as conn:
        me = conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_user["id"],)).fetchone()
    if not me:
        raise HTTPException(404, "User not found")

    ok = db.update_interest_status(interest_id, me["tg_id"], "declined")
    if not ok:
        raise HTTPException(404, "Interest not found or not yours")

    return {"ok": True}


# ── Health ────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "ts": int(time.time())}
