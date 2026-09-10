import os
import sys
import httpx
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import uvicorn

# Ensure UTF-8 output encoding for Windows command line terminals
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ==========================================
# 1. CONFIGURATION & CONSTANTS
# ==========================================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv(
    "LINE_CHANNEL_ACCESS_TOKEN",
    "KvNZvrpSbwGYFBu76Y8ximlw/LnKmoDTisOFzkyCoFo8T/REVrytbOCjJdo+tYu662xMfG4YQs/fzLjjTZTGF31q5+OshzTzI34aOw5KzLsuXYdExswTFruj/lzfLQudFbK3Dh66t9YpP4hT7HHVXAdB04t89/1O/w1cDnyilFU="
)
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "12d9362f07b746e885d8f5a87712a35d")
LINE_USER_ID = os.getenv("LINE_USER_ID", "U4776c4283302343cebd85ab4cefbf2f9")
APP_URL = os.getenv("RENDER_EXTERNAL_URL", "https://tradsignal.onrender.com")

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")
SCALPING_MODE = True

# Light Strategy State Tracking
buy_streak = 0
sell_streak = 0
active_dir = 0          # 0: ว่าง, 1: ถือ BUY, -1: ถือ SELL
entry_price = 0.0
sl_level = 0.0
tp1_level = 0.0
tp2_level = 0.0
tp3_level = 0.0
entry_atr = 0.0
last_processed_candle_time = None

app = FastAPI()

# ==========================================
# 2. HELPER FUNCTIONS & INDICATORS
# ==========================================
def get_thai_time(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.now(BANGKOK_TZ).strftime(fmt)

def get_current_session_tf() -> tuple[str, str]:
    """
    คืนค่า (api_interval, display_label) ตามช่วงเวลาไทย
    - ช่วงเช้า (ก่อน 12:00): 5 นาที (5min / 5m)
    - ช่วงบ่าย (12:00 เป็นต้นไป): 15 นาที (15min / 15m)
    """
    current_hour = datetime.now(BANGKOK_TZ).hour
    if current_hour < 12:
        return "5min", "5m"
    else:
        return "15min", "15m"

def calculate_wma(series: pd.Series, period: int) -> pd.Series:
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

def calculate_hma(series: pd.Series, period: int = 20) -> pd.Series:
    """Hull Moving Average (HMA) Baseline"""
    half_wma = calculate_wma(series, int(period / 2)) * 2
    full_wma = calculate_wma(series, period)
    diff = half_wma - full_wma
    return calculate_wma(diff, int(np.sqrt(period)))

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df['high'] - df['low']
    high_cp = (df['high'] - df['close'].shift()).abs()
    low_cp = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def fetch_gold_data(interval: str = "5min", outputsize: int = 100) -> pd.DataFrame:
    url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval={interval}&outputsize={outputsize}&apikey={TWELVE_DATA_API_KEY}"
    with httpx.Client(timeout=10.0) as client:
        res = client.get(url)
        data = res.json()
    
    if "values" not in data:
        raise Exception(f"Failed to fetch data: {data.get('message', 'Unknown error')}")
        
    df = pd.DataFrame(data["values"])
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)
    df = df.iloc[::-1].reset_index(drop=True)
    return df

def fetch_live_price():
    try:
        url = f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={TWELVE_DATA_API_KEY}"
        with httpx.Client(timeout=8.0) as client:
            res = client.get(url)
            data = res.json()
            if "price" in data:
                return float(data["price"])
    except Exception as e:
        print(f"Fetch live price error: {e}")
    
    try:
        df = fetch_gold_data(interval="1min", outputsize=5)
        return float(df.iloc[-1]['close'])
    except Exception:
        return None

# ==========================================
# 3. LINE MESSAGING & KEEP-ALIVE
# ==========================================
async def send_line_message(text: str):
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {"messages": [{"type": "text", "text": text}]}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=headers)
            if res.status_code != 200:
                print(f"[{get_thai_time()}] LINE Broadcast Error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"[{get_thai_time()}] Network Error in send_line_message: {e}")

async def reply_line_message(reply_token: str, text: str):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=headers)
            if res.status_code != 200:
                print(f"[{get_thai_time()}] LINE Reply Error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"[{get_thai_time()}] Network Error in reply_line_message: {e}")

async def keep_alive():
    """ยิง Ping เข้าหาตัวเองทุก 10 นาทีเพื่อป้องกัน Render Sleep Mode"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(APP_URL)
            print(f"[{get_thai_time()}] Keep-Alive Ping Status: {res.status_code}")
    except Exception as e:
        print(f"[{get_thai_time()}] Keep-Alive Ping Failed: {e}")

# ==========================================
# 4. CORE LIGHT SIGNAL SCANNER (AUTO TF 5M / 15M)
# ==========================================
async def check_signal():
    global SCALPING_MODE, buy_streak, sell_streak
    global active_dir, entry_price, sl_level, tp1_level, tp2_level, tp3_level, entry_atr
    global last_processed_candle_time

    if not SCALPING_MODE:
        return

    # กฎระบบ Light: หยุดเทรดหลัง 19:00 น. (เวลาไทย) เพื่อเลี่ยงตลาดสหรัฐฯ และข่าวแรง
    current_hour = datetime.now(BANGKOK_TZ).hour
    if current_hour >= 19:
        return

    # กำหนด Timeframe อัตโนมัติตามช่วงเวลา
    interval, tf_label = get_current_session_tf()

    try:
        df = fetch_gold_data(interval=interval, outputsize=100)
        df['hma'] = calculate_hma(df['close'], period=20)
        df['rsi'] = calculate_rsi(df['close'], period=14)
        df['atr'] = calculate_atr(df, period=14)

        closed_bar = df.iloc[-2]
        prev_bar = df.iloc[-3]
        candle_time = closed_bar.get('datetime', str(closed_bar.name))

        # ตรวจสอบแท่งเทียนใหม่เพื่อป้องกันการประมวลผลซ้ำในแท่งเดิม
        if candle_time == last_processed_candle_time:
            return
        last_processed_candle_time = candle_time

        c_close = float(closed_bar['close'])
        c_high = float(closed_bar['high'])
        c_low = float(closed_bar['low'])
        c_hma = float(closed_bar['hma'])
        p_close = float(prev_bar['close'])
        p_hma = float(prev_bar['hma'])
        rsi_val = float(closed_bar['rsi'])
        atr_val = float(closed_bar['atr'])

        hma_trend_up = c_hma > p_hma
        hma_trend_down = c_hma < p_hma

        # 1. จัดการ Trailing Stop และการปิดรอบออเดอร์
        if active_dir == 1:
            if c_low <= sl_level:
                await send_line_message(f"🛑 [Light BUY 2 Closed | TF: {tf_label}]\nชน Stop Loss ที่ {sl_level:.2f}\n🕒 {get_thai_time()}")
                active_dir = 0
            elif c_high >= tp3_level:
                await send_line_message(f"🎉 [Light BUY 2 Closed | TF: {tf_label}]\nถึงเป้าหมายสูงสุด TP3 ที่ {tp3_level:.2f}\n🕒 {get_thai_time()}")
                active_dir = 0
            else:
                if (c_high - entry_price) >= (entry_atr * 1.0):
                    new_sl = c_high - (entry_atr * 1.0)
                    if new_sl > sl_level:
                        sl_level = new_sl
                        await send_line_message(f"🔄 [Light Trailing SL | TF: {tf_label}]\nยกจุดตัดขาดทุนฝั่ง BUY ขึ้นมาที่ {sl_level:.2f}")

        elif active_dir == -1:
            if c_high >= sl_level:
                await send_line_message(f"🛑 [Light SELL 2 Closed | TF: {tf_label}]\nชน Stop Loss ที่ {sl_level:.2f}\n🕒 {get_thai_time()}")
                active_dir = 0
            elif c_low <= tp3_level:
                await send_line_message(f"🎉 [Light SELL 2 Closed | TF: {tf_label}]\nถึงเป้าหมายสูงสุด TP3 ที่ {tp3_level:.2f}\n🕒 {get_thai_time()}")
                active_dir = 0
            else:
                if (entry_price - c_low) >= (entry_atr * 1.0):
                    new_sl = c_low + (entry_atr * 1.0)
                    if new_sl < sl_level:
                        sl_level = new_sl
                        await send_line_message(f"🔄 [Light Trailing SL | TF: {tf_label}]\nลดจุดตัดขาดทุนฝั่ง SELL ลงมาที่ {sl_level:.2f}")

        # 2. ตรวจสอบเงื่อนไขการตัดเส้น Baseline
        raw_buy = (c_close > c_hma and p_close <= p_hma) and hma_trend_up and (rsi_val > 50)
        raw_sell = (c_close < c_hma and p_close >= p_hma) and hma_trend_down and (rsi_val < 50)

        if raw_buy:
            buy_streak += 1
            sell_streak = 0
        elif raw_sell:
            sell_streak += 1
            buy_streak = 0

        # 3. แจ้งเตือนสัญญาณพร้อม Timeframe
        # --- สัญญาณไม้ที่ 1 (เตือนเฝ้าระวัง) ---
        if raw_buy and buy_streak == 1:
            msg = (
                f"⚠️ [Light Alert | TF: {tf_label}] สัญญาณ BUY 1\n"
                f"═════════════════\n"
                f"💵 ราคาปัจจุบัน: {c_close:.2f}\n"
                f"💡 เฝ้าระวังเตรียมตัว ยังไม่ต้องเข้าออเดอร์ตามกฎ Light\n"
                f"📊 RSI: {rsi_val:.1f} | ATR: {atr_val:.2f}\n"
                f"🕒 {get_thai_time()}"
            )
            await send_line_message(msg)

        elif raw_sell and sell_streak == 1:
            msg = (
                f"⚠️ [Light Alert | TF: {tf_label}] สัญญาณ SELL 1\n"
                f"═════════════════\n"
                f"💵 ราคาปัจจุบัน: {c_close:.2f}\n"
                f"💡 เฝ้าระวังเตรียมตัว ยังไม่ต้องเข้าออเดอร์ตามกฎ Light\n"
                f"📊 RSI: {rsi_val:.1f} | ATR: {atr_val:.2f}\n"
                f"🕒 {get_thai_time()}"
            )
            await send_line_message(msg)

        # --- สัญญาณไม้ที่ 2 (ยืนยันเข้าออเดอร์ + คำนวณ High R:R) ---
        elif raw_buy and buy_streak >= 2 and active_dir != 1:
            entry_price = c_close
            entry_atr = atr_val
            sl_level = entry_price - (1.0 * atr_val)
            tp1_level = entry_price + (2.0 * atr_val)
            tp2_level = entry_price + (3.5 * atr_val)
            tp3_level = entry_price + (5.0 * atr_val)
            active_dir = 1

            msg = (
                f"🟢 [Light Entry | TF: {tf_label}] ยืนยันสัญญาณ BUY 2!\n"
                f"═════════════════\n"
                f"💵 จุดเข้า (Entry): {entry_price:.2f}\n"
                f"🛑 ตัดขาดทุน (SL 1.0R): {sl_level:.2f}\n"
                f"🎯 เป้าหมาย TP1 (1:2.0): {tp1_level:.2f}\n"
                f"🎯 เป้าหมาย TP2 (1:3.5): {tp2_level:.2f}\n"
                f"🎯 เป้าหมาย TP3 (1:5.0): {tp3_level:.2f}\n"
                f"═════════════════\n"
                f"📈 Baseline HMA: {c_hma:.2f} | RSI: {rsi_val:.1f}\n"
                f"🕒 {get_thai_time()}"
            )
            await send_line_message(msg)

        elif raw_sell and sell_streak >= 2 and active_dir != -1:
            entry_price = c_close
            entry_atr = atr_val
            sl_level = entry_price + (1.0 * atr_val)
            tp1_level = entry_price - (2.0 * atr_val)
            tp2_level = entry_price - (3.5 * atr_val)
            tp3_level = entry_price - (5.0 * atr_val)
            active_dir = -1

            msg = (
                f"🔴 [Light Entry | TF: {tf_label}] ยืนยันสัญญาณ SELL 2!\n"
                f"═════════════════\n"
                f"💵 จุดเข้า (Entry): {entry_price:.2f}\n"
                f"🛑 ตัดขาดทุน (SL 1.0R): {sl_level:.2f}\n"
                f"🎯 เป้าหมาย TP1 (1:2.0): {tp1_level:.2f}\n"
                f"🎯 เป้าหมาย TP2 (1:3.5): {tp2_level:.2f}\n"
                f"🎯 เป้าหมาย TP3 (1:5.0): {tp3_level:.2f}\n"
                f"═════════════════\n"
                f"📈 Baseline HMA: {c_hma:.2f} | RSI: {rsi_val:.1f}\n"
                f"🕒 {get_thai_time()}"
            )
            await send_line_message(msg)

    except Exception as e:
        print(f"[{get_thai_time()}] Signal Scan Error: {e}")

# ==========================================
# 5. SUPPORT / RESISTANCE
# ==========================================
def get_daily_pivots():
    try:
        df_now = fetch_gold_data(interval="1min", outputsize=5)
        current_price = float(df_now.iloc[-1]['close'])

        url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=1day&outputsize=5&apikey={TWELVE_DATA_API_KEY}"
        with httpx.Client(timeout=10.0) as client:
            res = client.get(url)
            data = res.json()

        if "values" not in data or len(data["values"]) < 2:
            return None

        df_day = pd.DataFrame(data["values"])
        for col in ['open', 'high', 'low', 'close']:
            df_day[col] = df_day[col].astype(float)

        prev_day = df_day.iloc[1]
        h = float(prev_day['high'])
        l = float(prev_day['low'])
        c = float(prev_day['close'])

        pivot = (h + l + c) / 3
        return {
            "current_price": current_price,
            "pivot": pivot,
            "r1": (2 * pivot) - l,
            "s1": (2 * pivot) - h,
            "r2": pivot + (h - l),
            "s2": pivot - (h - l),
            "r3": h + 2 * (pivot - l),
            "s3": l - 2 * (h - pivot),
            "prev_high": h,
            "prev_low": l
        }
    except Exception as e:
        print(f"Pivot Calculation Error: {e}")
        return None

def get_1h_range():
    try:
        df = fetch_gold_data(interval="1min", outputsize=60)
        high_1h = float(df['high'].max())
        low_1h = float(df['low'].min())
        return {
            "current": float(df.iloc[-1]['close']),
            "high": high_1h,
            "low": low_1h,
            "range": high_1h - low_1h
        }
    except Exception as e:
        return None

# ==========================================
# 6. LIFESPAN & FASTAPI WEBHOOK ROUTER
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler(timezone=BANGKOK_TZ)
    # ตรวจสอบสัญญาณทุก 15 นาที (0, 15, 30, 45) ที่วินาทีที่ 15
    scheduler.add_job(check_signal, 'cron', minute='0,15,30,45', second='15')
    # ยิง Ping ป้องกัน Sleep ทุก 10 นาที
    scheduler.add_job(keep_alive, 'interval', minutes=10)
    scheduler.start()
    print("🚀 Light Bot Schedulers Started!")
    yield
    scheduler.shutdown()

app.router.lifespan_context = lifespan

@app.post("/webhook")
async def line_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"status": "invalid json"}

    events = data.get("events", [])
    for event in events:
        if event.get("type") == "message" and event["message"].get("type") == "text":
            user_text = event["message"]["text"].strip().lower()
            reply_token = event.get("replyToken")

            if user_text in ["ราคา", "price", "gold", "ทอง"]:
                current_price = fetch_live_price()
                if current_price:
                    reply_msg = f"💰 ราคาทองคำล่าสุด (XAU/USD): {current_price:.2f}\n🕒 {get_thai_time()}"
                else:
                    reply_msg = "❌ ไม่สามารถดึงราคาล่าสุดได้ในขณะนี้"
                await reply_line_message(reply_token, reply_msg)

            elif user_text in ["สถานะ", "status"]:
                _, tf_label = get_current_session_tf()
                interval, _ = get_current_session_tf()
                df = fetch_gold_data(interval=interval, outputsize=60)
                df['hma'] = calculate_hma(df['close'], period=20)
                df['rsi'] = calculate_rsi(df['close'], period=14)
                last_bar = df.iloc[-1]
                trend = "🟢 Bullish Zone" if last_bar['close'] > last_bar['hma'] else "🔴 Bearish Zone"
                reply_msg = (
                    f"📊 สถานะระบบ Light (TF: {tf_label})\n"
                    f"═════════════════\n"
                    f"💵 ราคา: {last_bar['close']:.2f}\n"
                    f"📈 แนวโน้ม: {trend}\n"
                    f"📉 RSI: {last_bar['rsi']:.1f}\n"
                    f"🎯 Buy Streak: {buy_streak} | Sell Streak: {sell_streak}\n"
                    f"💼 Active Trade: {'BUY' if active_dir == 1 else 'SELL' if active_dir == -1 else 'NONE'}"
                )
                await reply_line_message(reply_token, reply_msg)

            elif user_text in ["แนวรับแนวต้าน", "pivot"]:
                pivots = get_daily_pivots()
                if pivots:
                    reply_msg = (
                        f"🎯 กรอบแนวรับ-แนวต้าน วันนี้ (XAU/USD)\n"
                        f"═════════════════\n"
                        f"💵 ราคาปัจจุบัน: {pivots['current_price']:.2f}\n"
                        f"📊 กรอบเมื่อวาน: H {pivots['prev_high']:.2f} | L {pivots['prev_low']:.2f}\n"
                        f"═════════════════\n"
                        f"🔴 R3: {pivots['r3']:.2f} | R2: {pivots['r2']:.2f} | R1: {pivots['r1']:.2f}\n"
                        f"⚖️ Pivot กลาง: {pivots['pivot']:.2f}\n"
                        f"🟢 S1: {pivots['s1']:.2f} | S2: {pivots['s2']:.2f} | S3: {pivots['s3']:.2f}"
                    )
                else:
                    reply_msg = "❌ ไม่สามารถดึงข้อมูลแนวรับ-แนวต้านได้"
                await reply_line_message(reply_token, reply_msg)

            elif user_text in ["กรอบ 1 ชม", "1h range"]:
                data_1h = get_1h_range()
                if data_1h:
                    reply_msg = (
                        f"⏱️ กรอบราคา 1 ชั่วโมงล่าสุด\n"
                        f"═════════════════\n"
                        f"💵 ราคาปัจจุบัน: {data_1h['current']:.2f}\n"
                        f"🔺 High: {data_1h['high']:.2f} | 🔻 Low: {data_1h['low']:.2f}\n"
                        f"📏 ความกว้าง: {data_1h['range']:.2f} จุด"
                    )
                else:
                    reply_msg = "❌ ไม่สามารถดึงกรอบราคา 1 ชั่วโมงได้"
                await reply_line_message(reply_token, reply_msg)

            elif user_text in ["โหมดสายซิ่ง", "เปิดโหมดสายซิ่ง", "ปิดโหมดสายซิ่ง"]:
                global SCALPING_MODE
                if "เปิด" in user_text:
                    SCALPING_MODE = True
                elif "ปิด" in user_text:
                    SCALPING_MODE = False
                else:
                    SCALPING_MODE = not SCALPING_MODE
                status_text = "🟢 เปิดใช้งาน (Active)" if SCALPING_MODE else "🔴 ปิดใช้งาน (Paused)"
                await reply_line_message(reply_token, f"⚙️ การแจ้งเตือนระบบ Light: {status_text}")

    return {"status": "ok"}

@app.get("/")
def home():
    _, tf_label = get_current_session_tf()
    return {"status": "Light XAUUSD Bot Running", "active_tf": tf_label, "time": get_thai_time()}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
