import os
import httpx
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ==========================================
# 1. CONFIGURATION & CONSTANTS
# ==========================================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")
SCALPING_MODE = True

# GTPro State Tracking
buy_streak = 0
sell_streak = 0
last_signal = None

app = FastAPI()

# ==========================================
# 2. HELPER FUNCTIONS & INDICATORS
# ==========================================
def get_thai_time(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.now(BANGKOK_TZ).strftime(fmt)

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

def fetch_gold_data(interval: str = "1min", outputsize: int = 100) -> pd.DataFrame:
    """ดึงข้อมูลราคาทองคำ XAU/USD จาก Twelve Data API"""
    url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval={interval}&outputsize={outputsize}&apikey={TWELVE_DATA_API_KEY}"
    with httpx.Client(timeout=10.0) as client:
        res = client.get(url)
        data = res.json()
    
    if "values" not in data:
        raise Exception(f"Failed to fetch data: {data.get('message', 'Unknown error')}")
        
    df = pd.DataFrame(data["values"])
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)
    df = df.iloc[::-1].reset_index(drop=True)  # เรียงจากเก่าไปใหม่
    return df

# ==========================================
# 3. LINE MESSAGING FUNCTIONS
# ==========================================
async def send_line_message(text: str):
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {"messages": [{"type": "text", "text": text}]}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload, headers=headers)

async def reply_line_message(reply_token: str, text: str):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload, headers=headers)

# ==========================================
# 4. CORE GTPRO SIGNAL SCANNER
# ==========================================
async def check_signal():
    global last_signal, SCALPING_MODE, buy_streak, sell_streak
    
    if not SCALPING_MODE:
        return

    # กฎ GTPro: ตรวจสอบเวลาเทรด (ห้ามเทรดหลัง 19:00 น. เวลาไทย)
    current_hour = datetime.now(BANGKOK_TZ).hour
    if current_hour >= 19:
        return

    try:
        df = fetch_gold_data(interval="1min", outputsize=100)
        df['hma'] = calculate_hma(df['close'], period=20)
        df['rsi'] = calculate_rsi(df['close'], period=14)
        df['atr'] = calculate_atr(df, period=14)

        closed_bar = df.iloc[-2]
        prev_bar = df.iloc[-3]

        entry_price = float(closed_bar['close'])
        rsi_val = float(closed_bar['rsi'])
        atr_val = float(closed_bar['atr'])

        hma_trend_up = closed_bar['hma'] > prev_bar['hma']
        hma_trend_down = closed_bar['hma'] < prev_bar['hma']

        # เงื่อนไขตัดข้าม Baseline
        raw_buy = (closed_bar['close'] > closed_bar['hma'] and prev_bar['close'] <= prev_bar['hma']) and hma_trend_up and (rsi_val > 50)
        raw_sell = (closed_bar['close'] < closed_bar['hma'] and prev_bar['close'] >= prev_bar['hma']) and hma_trend_down and (rsi_val < 50)

        # กฎ GTPro: นับสัญญาณรอบที่ 2 (Second Signal Confirmation)
        if raw_buy:
            buy_streak += 1
            sell_streak = 0
        elif raw_sell:
            sell_streak += 1
            buy_streak = 0

        # ส่งสัญญาณเมื่อเข้าเงื่อนไขไม้ที่ 2 เป็นต้นไป
        if raw_buy and buy_streak >= 2 and last_signal != "BUY_2":
            sl_level = entry_price - (1.5 * atr_val)
            tp1_level = entry_price + (1.5 * atr_val)
            tp2_level = entry_price + (2.5 * atr_val)
            tp3_level = entry_price + (3.5 * atr_val)

            msg = (
                f"🟢 GTPro BUY Signal (2nd Confirmed!)\n"
                f"═════════════════\n"
                f"💵 Entry: {entry_price:.2f}\n"
                f"🛑 Stop Loss: {sl_level:.2f}\n"
                f"🎯 TP1 (1.5R): {tp1_level:.2f}\n"
                f"🎯 TP2 (2.5R): {tp2_level:.2f}\n"
                f"🎯 TP3 (3.5R): {tp3_level:.2f}\n"
                f"═════════════════\n"
                f"📊 RSI: {rsi_val:.1f} | ATR: {atr_val:.2f}\n"
                f"🕒 เวลาไทย: {get_thai_time()}"
            )
            await send_line_message(msg)
            last_signal = "BUY_2"

        elif raw_sell and sell_streak >= 2 and last_signal != "SELL_2":
            sl_level = entry_price + (1.5 * atr_val)
            tp1_level = entry_price - (1.5 * atr_val)
            tp2_level = entry_price - (2.5 * atr_val)
            tp3_level = entry_price - (3.5 * atr_val)

            msg = (
                f"🔴 GTPro SELL Signal (2nd Confirmed!)\n"
                f"═════════════════\n"
                f"💵 Entry: {entry_price:.2f}\n"
                f"🛑 Stop Loss: {sl_level:.2f}\n"
                f"🎯 TP1 (1.5R): {tp1_level:.2f}\n"
                f"🎯 TP2 (2.5R): {tp2_level:.2f}\n"
                f"🎯 TP3 (3.5R): {tp3_level:.2f}\n"
                f"═════════════════\n"
                f"📊 RSI: {rsi_val:.1f} | ATR: {atr_val:.2f}\n"
                f"🕒 เวลาไทย: {get_thai_time()}"
            )
            await send_line_message(msg)
            last_signal = "SELL_2"

    except Exception as e:
        print(f"[{get_thai_time()}] Signal Scan Error: {e}")

# ==========================================
# 5. SUPPORT / RESISTANCE & 15M UPDATE
# ==========================================
def get_daily_pivots():
    try:
        df_now = fetch_gold_data(interval="1min", outputsize=10)
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
            "prev_high": h, "prev_low": l
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

# async def send_price_update_15m():
#     try:
#         df = fetch_gold_data(interval="1min", outputsize=60)
#         df['hma'] = calculate_hma(df['close'], period=20)
#         df['rsi'] = calculate_rsi(df['close'], period=14)

#         last_bar = df.iloc[-1]
#         price = float(last_bar['close'])
#         rsi_val = float(last_bar['rsi'])
#         trend_text = "🟢 ขาขึ้น (Bullish)" if price > last_bar['hma'] else "🔴 ขาลง (Bearish)"

#         msg = (
#             f"⏰ สรุปราคาทองคำรอบ 15 นาที\n"
#             f"═════════════════\n"
#             f"💰 ราคาล่าสุด: {price:.2f}\n"
#             f"📈 แนวโน้ม GTPro: {trend_text}\n"
#             f"📊 RSI (14): {rsi_val:.1f}\n"
#             f"🕒 เวลาไทย: {get_thai_time('%H:%M')} น.\n"
#             f"═════════════════"
#         )
#         await send_line_message(msg)
#     except Exception as e:
#         print(f"Price update error: {e}")

# ==========================================
# 6. FASTAPI WEBHOOK & LIFESPAN
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler(timezone=BANGKOK_TZ)
    scheduler.add_job(check_signal, 'cron', second='5')
    # scheduler.add_job(send_price_update_15m, 'cron', minute='0,15,30,45', second='0')
    scheduler.start()
    print("🚀 GTPro Bot Schedulers Started!")
    yield
    scheduler.shutdown()

app.router.lifespan_context = lifespan

@app.post("/webhook")
async def line_webhook(request: Request):
    data = await request.json()
    events = data.get("events", [])
    
    for event in events:
        if event.get("type") == "message" and event["message"].get("type") == "text":
            user_text = event["message"]["text"].strip().lower()
            reply_token = event.get("replyToken")

            if user_text in ["ราคา", "price", "gold", "ทอง"]:
                df = fetch_gold_data(interval="1min", outputsize=10)
                current_price = float(df.iloc[-1]['close'])
                reply_msg = f"💰 ราคาทองคำล่าสุด (XAU/USD): {current_price:.2f}\n🕒 {get_thai_time()}"
                await reply_line_message(reply_token, reply_msg)

            elif user_text in ["สถานะ", "status"]:
                df = fetch_gold_data(interval="1min", outputsize=60)
                df['hma'] = calculate_hma(df['close'], period=20)
                df['rsi'] = calculate_rsi(df['close'], period=14)
                last_bar = df.iloc[-1]
                trend = "🟢 Bullish Zone" if last_bar['close'] > last_bar['hma'] else "🔴 Bearish Zone"
                reply_msg = (
                    f"📊 สถานะ GTPro (TF 1m)\n"
                    f"═════════════════\n"
                    f"💵 ราคา: {last_bar['close']:.2f}\n"
                    f"📈 แนวโน้ม: {trend}\n"
                    f"📉 RSI: {last_bar['rsi']:.1f}\n"
                    f"🎯 Buy Count: {buy_streak} | Sell Count: {sell_streak}"
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
                await reply_line_message(reply_token, f"⚙️ โหมดสายซิ่ง GTPro: {status_text}")

    return {"status": "ok"}

@app.get("/")
def home():
    return {"status": "GTPro XAUUSD Bot Running", "time": get_thai_time()}
