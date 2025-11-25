import os
import requests
import datetime
import time
from threading import Thread
from flask import Flask
from oandapyV20 import API
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.instruments as instruments

# =================== CREDENTIALS (ENV) ===================
# Credentials must be provided via environment variables to avoid
# committing secrets into the repository. See `.env.example`.
OANDA_API_KEY    = os.environ.get("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.environ.get("OANDA_ACCOUNT_ID")
OANDA_ENV        = os.environ.get("OANDA_ENV", "practice")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID          = os.environ.get("CHAT_ID")

# Fail fast if required credentials are missing (prevents accidental leaks)
missing = [k for k in ("OANDA_API_KEY", "OANDA_ACCOUNT_ID", "TELEGRAM_TOKEN", "CHAT_ID") if not os.environ.get(k)]
if missing:
    print("Missing required environment variables: " + ", ".join(missing))
    raise SystemExit(1)

api = API(access_token=OANDA_API_KEY, environment=OANDA_ENV)

SYMBOL           = "US100_USD"
POSITION_SIZE    = 248
ENTRY_START      = "10:00"
ENTRY_END        = "10:15"
already_traded_today = False
app = Flask(__name__)

def log_and_notify(msg):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[SILVER] {timestamp} → {msg}\n"
    with open("silver.log", "a", encoding="utf-8") as f:
        f.write(line)
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": f"Silver Bullet\n{msg}"},
            timeout=10
        )
    except:
        pass

def get_price():
    try:
        r = instruments.InstrumentsCandles(instrument=SYMBOL, params={"count": 1, "granularity": "M1", "price": "M"})
        api.request(r)
        return round(float(r.response["candles"][0]["mid"]["c"]), 1)
    except:
        return None

def get_candles(count=20, granularity="M15"):
    try:
        params = {"count": count, "granularity": granularity, "price": "M"}
        r = instruments.InstrumentsCandles(instrument=SYMBOL, params=params)
        api.request(r)
        return [c for c in r.response["candles"] if c["complete"]]
    except:
        return []

def detect_silver_fvg():
    candles = get_candles(10, "M15")
    if len(candles) < 3:
        return None
    c0, c1, c2 = candles[-3], candles[-2], candles[-1]
    h0 = float(c0["mid"]["h"])
    l0 = float(c0["mid"]["l"])
    h2 = float(c2["mid"]["h"])
    l2 = float(c2["mid"]["l"])

    if l2 > h0:
        return {"type": "bullish", "zone_bottom": h0, "zone_top": l2}
    if h2 < l0:
        return {"type": "bearish", "zone_bottom": h2, "zone_top": l0}
    return None

def place_trade(direction, zone):
    price = get_price()
    if not price: return
    distance = 1.5
    sl = round(zone["zone_bottom"] - distance if direction == "long" else zone["zone_top"] + distance, 1)
    tp = round(price + abs(price - sl) * 3 if direction == "long" else price - abs(sl - price) * 3, 1)
    units = POSITION_SIZE if direction == "long" else -POSITION_SIZE

    data = {
        "order": {
            "instrument": SYMBOL,
            "units": str(units),
            "type": "MARKET",
            "timeInForce": "FOK",
            "stopLossOnFill": {"price": str(sl)},
            "takeProfitOnFill": {"price": str(tp)}
        }
    }
    try:
        r = orders.OrderCreate(OANDA_ACCOUNT_ID, data=data)
        api.request(r)
        log_and_notify(f"SILVER BULLET {direction.upper()} FIRED\nEntry: {price}\nSL: {sl} | TP: {tp}\nZone: {zone['zone_bottom']}-{zone['zone_top']}")
    except Exception as e:
        log_and_notify(f"Order failed: {str(e)}")

def silver_loop():
    log_and_notify("SILVER BULLET BOT STARTED – Hunting 10:00–10:15 NY")
    global already_traded_today
    while True:
        now = datetime.datetime.now()
        t = now.strftime("%H:%M")
        if now.hour == 0 and now.minute < 5:
            already_traded_today = False
            log_and_notify("New day – Silver Bullet armed")

        if ENTRY_START <= t <= ENTRY_END and not already_traded_today:
            log_and_notify("WINDOW OPEN – Scanning for FVG...")
            fvg = detect_silver_fvg()
            if fvg:
                price = get_price()
                if price and (fvg["zone_bottom"] - 10 <= price <= fvg["zone_top"] + 10):
                    direction = "long" if fvg["type"] == "bullish" else "short"
                    place_trade(direction, fvg)
                    already_traded_today = True
                else:
                    log_and_notify(f"FVG found but price {price} not in zone")
        time.sleep(15)

@app.route("/")
def home():
    return "<h1>Silver Bullet Bot LIVE</h1><p>Log → <a href='/silver'>/silver</a></p>"

@app.route("/silver")
def silver_log():
    try:
        with open("silver.log", "r", encoding="utf-8") as f:
            return f"<pre>{f.read()[-8000:]}</pre><meta http-equiv='refresh' content='5'>"
    except:
        return "<pre>Silver Bullet log starting...</pre>"

if __name__ == "__main__":
    Thread(target=silver_loop, daemon=True).start()
    log_and_notify("SILVER BULLET BOT FULLY LIVE & ARMED")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))