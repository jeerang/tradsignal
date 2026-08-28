import os
import time
import asyncio
from contextlib import asynccontextmanager
import httpx
import ccxt
import pandas as pd
import numpy as np
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Request
from datetime import datetime
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

# ตั้งค่าโซนเวลาไทย
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

def get_thai_time(format_str="%H:%M:%S"):
    return datetime.now(BANGKOK_TZ).strftime(format_str)

TWELVE_DATA_API_KEY ="12d9362f07b746e885d8f5a87712a35d"

def fetch_gold_data():
    url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=1min&outputsize=100&apikey={TWELVE_DATA_API_KEY}"
    with httpx.Client(timeout=10.0) as client:
        res = client.get(url)
        data = res.json()
        
    if "values" not in data:
        raise Exception(f"Twelve Data Error: {data.get('message', 'No data')}")
        
    df = pd.DataFrame(data["values"])
    # แปลงชนิดข้อมูลตัวเลข
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)
        
    # Twelve Data เรียงจากใหม่ไปเก่า จึงต้องกลับลำดับให้อดีตอยู่บน ปัจจุบันอยู่ล่าง
    df = df.iloc[::-1].reset_index(drop=True)
    return df

exchange = ccxt.binance({
    'options': {'defaultType': 'future'},
    'enableRateLimit': True,
    'timeout': 10000
})
symbol = "XAU/USDT"
timeframe = "1m"
last_signal = None

LINE_ACCESS_TOKEN = "KvNZvrpSbwGYFBu76Y8ximlw/LnKmoDTisOFzkyCoFo8T/REVrytbOCjJdo+tYu662xMfG4YQs/fzLjjTZTGF31q5+OshzTzI34aOw5KzLsuXYdExswTFruj/lzfLQudFbK3Dh66t9YpP4hT7HHVXAdB04t89/1O/w1cDnyilFU="
LINE_USER_ID = "U4776c4283302343cebd85ab4cefbf2f9"

async def send_line_message(text: str):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    body = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text}]
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post("https://api.line.me/v2/bot/message/push", headers=headers, json=body)
            print(f"LINE Response: {res.status_code}, Body: {res.text}")
    except Exception as e:
        print(f"Error sending LINE message: {e}")

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_supertrend(df, period=7, multiplier=1.2):
    high = df['high']
    low = df['low']
    close = df['close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    hl2 = (high + low) / 2
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    final_upper = np.zeros(len(df))
    final_lower = np.zeros(len(df))
    supertrend = np.zeros(len(df))
    direction = np.zeros(len(df))

    for i in range(1, len(df)):
        if basic_upper.iloc[i] < final_upper[i-1] or close.iloc[i-1] > final_upper[i-1]:
            final_upper[i] = basic_upper.iloc[i]
        else:
            final_upper[i] = final_upper[i-1]

        if basic_lower.iloc[i] > final_lower[i-1] or close.iloc[i-1] < final_lower[i-1]:
            final_lower[i] = basic_lower.iloc[i]
        else:
            final_lower[i] = final_lower[i-1]

        if direction[i-1] == 1:
            if close.iloc[i] < final_lower[i]:
                direction[i] = -1
                supertrend[i] = final_upper[i]
            else:
                direction[i] = 1
                supertrend[i] = final_lower[i]
        else:
            if close.iloc[i] > final_upper[i]:
                direction[i] = 1
                supertrend[i] = final_lower[i]
            else:
                direction[i] = -1
                supertrend[i] = final_upper[i]

    df['atr'] = atr
    df['supertrend'] = supertrend
    df['direction'] = direction
    return df

async def check_signal():
    global last_signal
    try:
        df = fetch_gold_data()
        df['rsi'] = calculate_rsi(df['close'], period=14)
        df = calculate_supertrend(df, period=7, multiplier=1.2)

        closed_bar = df.iloc[-2]
        prev_bar = df.iloc[-3]

        entry_price = float(closed_bar['close'])
        rsi_val = float(closed_bar['rsi'])
        atr_val = float(closed_bar['atr'])
        curr_dir = closed_bar['direction']
        prev_dir = prev_bar['direction']

        # Log ตรวจสอบค่าทุกนาที
        print(f"[{get_thai_time()}] Scan: Price={entry_price:.2f} | RSI={rsi_val:.1f} | Dir={prev_dir}->{curr_dir} | LastSig={last_signal}")

        # ตรวจสอบ BUY
        if prev_dir == -1 and curr_dir == 1:
            if rsi_val > 50:
                if last_signal != "BUY":
                    last_signal = "BUY"
                    sl = float(closed_bar['supertrend'])
                    tp1 = entry_price + (1.0 * atr_val)
                    tp2 = entry_price + (1.5 * atr_val)
                    tp3 = entry_price + (2.0 * atr_val)

                    msg = (
                        f"🟢 BUY Signal XAUUSD (TF: 1m)\n"
                        f"═════════════════\n"
                        f"🎯 Entry: {entry_price:.2f}\n"
                        f"🛑 SL: {sl:.2f}\n"
                        f"🎯 TP1: {tp1:.2f}\n"
                        f"🎯 TP2: {tp2:.2f}\n"
                        f"🎯 TP3: {tp3:.2f}\n"
                        f"═════════════════\n"
                        f"📊 RSI: {rsi_val:.1f} | ATR: {atr_val:.2f}\n"
                        f"🕒 เวลาไทย: {get_thai_time()}"
                    )
                    await send_line_message(msg)
                    print(f"[{get_thai_time()}] >>> BUY Signal Triggered & Sent!")
            else:
                print(f"[{get_thai_time()}] BUY condition met but filtered by RSI ({rsi_val:.1f} <= 50)")

        # ตรวจสอบ SELL
        elif prev_dir == 1 and curr_dir == -1:
            if rsi_val < 50:
                if last_signal != "SELL":
                    last_signal = "SELL"
                    sl = float(closed_bar['supertrend'])
                    tp1 = entry_price - (1.0 * atr_val)
                    tp2 = entry_price - (1.5 * atr_val)
                    tp3 = entry_price - (2.0 * atr_val)

                    msg = (
                        f"🔴 SELL Signal XAUUSD (TF: 1m)\n"
                        f"═════════════════\n"
                        f"🎯 Entry: {entry_price:.2f}\n"
                        f"🛑 SL: {sl:.2f}\n"
                        f"🎯 TP1: {tp1:.2f}\n"
                        f"🎯 TP2: {tp2:.2f}\n"
                        f"🎯 TP3: {tp3:.2f}\n"
                        f"═════════════════\n"
                        f"📊 RSI: {rsi_val:.1f} | ATR: {atr_val:.2f}\n"
                        f"🕒 เวลาไทย: {get_thai_time()}"
                    )
                    await send_line_message(msg)
                    print(f"[{get_thai_time()}] >>> SELL Signal Triggered & Sent!")
            else:
                print(f"[{get_thai_time()}] SELL condition met but filtered by RSI ({rsi_val:.1f} >= 50)")

    except Exception as e:
        print(f"[{get_thai_time()}] Scan Error: {e}")

async def send_price_update_15m():
    """ฟังก์ชันส่งสรุปราคาทองคำและเทรนด์เข้า LINE ทุกๆ 15 นาที"""
    try:
        df = fetch_gold_data()
        df['rsi'] = calculate_rsi(df['close'], period=14)
        df = calculate_supertrend(df, period=7, multiplier=1.2)

        last_bar = df.iloc[-1]
        price = float(last_bar['close'])
        rsi_val = float(last_bar['rsi'])
        direction = last_bar['direction']
        
        trend_text = "🟢 ขาขึ้น (Bullish)" if direction == 1 else "🔴 ขาลง (Bearish)"
        time_th = get_thai_time("%H:%M")

        msg = (
            f"⏰ สรุปราคาทองคำรอบ 15 นาที\n"
            f"═════════════════\n"
            f"💰 ราคาล่าสุด: {price:.2f}\n"
            f"📈 แนวโน้ม: {trend_text}\n"
            f"📊 RSI (14): {rsi_val:.1f}\n"
            f"🕒 เวลาไทย: {time_th} น.\n"
            f"═════════════════"
        )
        await send_line_message(msg)
        print(f"[{get_thai_time()}] 15-Minute Price Update Sent Successfully!")
    except Exception as e:
        print(f"[{get_thai_time()}] Error in 15m update: {e}")

def calculate_pivot_points(prev_day_bar):
    """คำนวณ Classic Pivot Points (แนวรับ-แนวต้านประจำวัน)"""
    h = float(prev_day_bar['high'])
    l = float(prev_day_bar['low'])
    c = float(prev_day_bar['close'])
    
    pivot = (h + l + c) / 3
    r1 = (2 * pivot) - l
    s1 = (2 * pivot) - h
    r2 = pivot + (h - l)
    s2 = pivot - (h - l)
    r3 = h + 2 * (pivot - l)
    s3 = l - 2 * (h - pivot)
    
    return {
        "pivot": pivot,
        "r1": r1, "r2": r2, "r3": r3,
        "s1": s1, "s2": s2, "s3": s3,
        "prev_high": h, "prev_low": l, "prev_close": c
    }

def get_tf_trend(symbol_tf, limit=100):
    """ดึงข้อมูล Timeframe ต่างๆ จากแหล่งข้อมูลเดียวกัน"""
    try:
        # ใช้ exchange เดียวกันกับระบบหลัก
        bars = exchange.fetch_ohlcv(symbol, timeframe=symbol_tf, limit=limit)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
        
        # แปลงชนิดข้อมูลตัวเลข
        for col in ['open', 'high', 'low', 'close', 'vol']:
            df[col] = df[col].astype(float)
            
        df['rsi'] = calculate_rsi(df['close'], period=14)
        df = calculate_supertrend(df, period=7, multiplier=1.2)
        
        last = df.iloc[-1]
        trend = "🟢 ขาขึ้น" if last['direction'] == 1 else "🔴 ขาลง"
        return trend, float(last['rsi']), df
    except Exception as e:
        print(f"Error fetching TF {symbol_tf}: {e}")
        return "⚪ ไม่ระบุ", 50.0, None

def get_daily_pivots():
    """คำนวณ Pivot Points จากแท่ง Day เมื่อวาน และดึงราคาล่าสุดของวันนี้"""
    try:
        # 1. ดึงราคาปัจจุบันล่าสุดจากฟังก์ชันหลัก
        df_now = fetch_gold_data()
        current_price = float(df_now.iloc[-1]['close'])
        
        # 2. ดึงข้อมูลแท่ง Day (หากใช้ Twelve Data หรือ Exchange)
        # ตัวอย่างสำหรับ Twelve Data:
        url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=1day&outputsize=5&apikey={TWELVE_DATA_API_KEY}"
        with httpx.Client(timeout=10.0) as client:
            res = client.get(url)
            data = res.json()
            
        if "values" not in data or len(data["values"]) < 2:
            return None
            
        df_day = pd.DataFrame(data["values"])
        for col in ['open', 'high', 'low', 'close']:
            df_day[col] = df_day[col].astype(float)
            
        # สำคัญ: Twelve Data เรียงจาก ใหม่ (0) -> เก่า (1, 2, ...)
        # values[0] คือแท่งของวันนี้ที่กำลังวิ่งอยู่
        # values[1] คือแท่งของเมื่อวานที่ปิดสมบูรณ์แล้ว
        prev_day = df_day.iloc[1] 
        h = float(prev_day['high'])
        l = float(prev_day['low'])
        c = float(prev_day['close'])

        # Classic Pivot Point Formula
        pivot = (h + l + c) / 3
        r1 = (2 * pivot) - l
        s1 = (2 * pivot) - h
        r2 = pivot + (h - l)
        s2 = pivot - (h - l)
        r3 = h + 2 * (pivot - l)
        s3 = l - 2 * (h - pivot)

        return {
            "current_price": current_price,
            "pivot": pivot,
            "r1": r1, "r2": r2, "r3": r3,
            "s1": s1, "s2": s2, "s3": s3,
            "prev_high": h, "prev_low": l, "prev_close": c
        }
    except Exception as e:
        print(f"Error calculating pivots: {e}")
        return None

def fetch_gold_news():
    """ดึงพาดหัวข่าวทองคำและเศรษฐกิจล่าสุดจาก RSS Feed"""
    try:
        url = "https://news.google.com/rss/search?q=gold+price+OR+forex+fed+economy&hl=en-US&gl=US&ceid=US:en"
        with httpx.Client(timeout=10.0) as client:
            res = client.get(url)
            root = ET.fromstring(res.content)
            items = root.findall('./channel/item')[:3]
            news_list = [f"• {item.find('title').text.split(' - ')[0]}" for item in items]
            return "\n".join(news_list)
    except Exception:
        return "• ตลาดจับตาตัวเลขเศรษฐกิจสหรัฐฯ และทิศทางดอกเบี้ย"

async def send_morning_briefing():
    """ส่งสรุปภาพรวม Multi-Timeframe + แนวรับแนวต้าน + ข่าว ทุก 06:00 น."""
    try:
        # 1. วิเคราะห์ Multi-Timeframe
        trend_1h, rsi_1h, _ = get_tf_trend('1h')
        trend_4h, rsi_4h, _ = get_tf_trend('4h')
        trend_1d, rsi_1d, df_day = get_tf_trend('1d')
        trend_1w, rsi_1w, _ = get_tf_trend('1w')
        trend_1m, rsi_1m, _ = get_tf_trend('1M')

        # 2. คำนวณแนวรับ-แนวต้านจากแท่งวันก่อนหน้า
        if df_day is not None and len(df_day) >= 2:
            prev_day = df_day.iloc[-2]
            current_price = float(df_day.iloc[-1]['close'])
            pivots = calculate_pivot_points(prev_day)
        else:
            return

        # 3. ข่าวสารเศรษฐกิจ
        news_summary = fetch_gold_news()
        today_str = datetime.now(BANGKOK_TZ).strftime("%d/%m/%Y")

        # 4. ประกอบข้อความ LINE
        msg = (
            f"🌅 สรุปบทวิเคราะห์ทองคำ (XAU/USD)\n"
            f"📅 ประจำวันที่: {today_str} (06:00 น.)\n"
            f"═════════════════\n"
            f"💵 ราคาปัจจุบัน: {current_price:.2f}\n\n"
            f"📊 โครงสร้างแนวโน้ม (Multi-TF):\n"
            f"• TF 1H  : {trend_1h} (RSI: {rsi_1h:.1f})\n"
            f"• TF 4H  : {trend_4h} (RSI: {rsi_4h:.1f})\n"
            f"• TF Day : {trend_1d} (RSI: {rsi_1d:.1f})\n"
            f"• TF Week: {trend_1w} (RSI: {rsi_1w:.1f})\n"
            f"• TF Month: {trend_1m} (RSI: {rsi_1m:.1f})\n"
            f"═════════════════\n"
            f"🎯 กรอบราคา & แนวรับ-แนวต้านวันนี้:\n"
            f"🔴 ต้าน 3 (R3): {pivots['r3']:.2f}\n"
            f"🔴 ต้าน 2 (R2): {pivots['r2']:.2f}\n"
            f"🔴 ต้าน 1 (R1): {pivots['r1']:.2f}\n"
            f"⚖️ Pivot กลาง: {pivots['pivot']:.2f}\n"
            f"🟢 รับ 1 (S1): {pivots['s1']:.2f}\n"
            f"🟢 รับ 2 (S2): {pivots['s2']:.2f}\n"
            f"🟢 รับ 3 (S3): {pivots['s3']:.2f}\n"
            f"═════════════════\n"
            f"📰 ข่าวเศรษฐกิจที่น่าสนใจ:\n"
            f"{news_summary}\n"
            f"═════════════════\n"
            f"💡 คำแนะนำ: หากราคายืนเหนือ Pivot ({pivots['pivot']:.2f}) เน้นย่อ Buy ตามเทรนด์ใหญ่"
        )

        await send_line_message(msg)
        print(f"[{get_thai_time()}] 06:00 AM Morning Briefing Sent Successfully!")

    except Exception as e:
        print(f"[{get_thai_time()}] Morning Briefing Error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler(timezone=BANGKOK_TZ)
    
    # 1. สแกนสัญญาณเทรดทุก 1 นาที
    scheduler.add_job(check_signal, 'cron', second='5')
    
    # 2. แจ้งราคาทุก 15 นาที
    scheduler.add_job(send_price_update_15m, 'cron', minute='0,15,30,45', second='0')
    
    # 3. ส่งบทวิเคราะห์ประจำวันทุก 06:00 น. (เวลาไทย)
    scheduler.add_job(send_morning_briefing, 'cron', hour=6, minute=0)
    
    scheduler.start()
    print("🚀 Schedulers Started: 1m Signal, 15m Price, 06:00 AM Briefing")
    yield
    scheduler.shutdown()

async def reply_line_message(reply_token: str, text: str):
    """ส่งข้อความตอบกลับด้วย replyToken (ไม่ต้องเสียโควต้า Push Message)"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    body = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}]
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=body)
            print(f"Reply status: {res.status_code}")
    except Exception as e:
        print(f"Error replying to LINE: {e}")

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def line_webhook(request: Request):
    data = await request.json()
    events = data.get("events", [])
    
    for event in events:
        if event.get("type") == "message" and event["message"].get("type") == "text":
            user_text = event["message"]["text"].strip().lower()
            reply_token = event.get("replyToken")
            
            # 1. ปุ่มเช็คราคา
            if user_text in ["ราคา", "price", "gold", "ทอง"]:
                try:
                    df = fetch_gold_data()
                    current_price = float(df.iloc[-1]['close'])
                    reply_msg = (
                        f"💰 ราคาทองคำล่าสุด (XAU/USD)\n"
                        f"═════════════════\n"
                        f"💵 ราคา: {current_price:.2f}\n"
                        f"🕒 เวลาไทย: {get_thai_time()}\n"
                        f"═════════════════"
                    )
                except Exception as e:
                    reply_msg = f"❌ ไม่สามารถดึงราคาได้: {e}"
                await reply_line_message(reply_token, reply_msg)
                
            # 2. ปุ่มเช็คสถานะ & RSI
            elif user_text in ["สถานะ", "status", "เช็คสัญญาณ", "signal"]:
                try:
                    df = fetch_gold_data()
                    df['rsi'] = calculate_rsi(df['close'], period=14)
                    df = calculate_supertrend(df, period=7, multiplier=1.2)
                    
                    last_bar = df.iloc[-1]
                    price = float(last_bar['close'])
                    rsi = float(last_bar['rsi'])
                    trend = "🟢 ขาขึ้น (BUY Zone)" if last_bar['direction'] == 1 else "🔴 ขาลง (SELL Zone)"
                    
                    reply_msg = (
                        f"📊 สถานะเทคนิคอล XAUUSD (TF: 1m)\n"
                        f"═════════════════\n"
                        f"💵 ราคาปัจจุบัน: {price:.2f}\n"
                        f"📈 เทรนด์: {trend}\n"
                        f"📉 RSI (14): {rsi:.2f}\n"
                        f"🕒 ตรวจสอบเมื่อ: {get_thai_time()}"
                    )
                except Exception as e:
                    reply_msg = f"❌ เกิดข้อผิดพลาด: {e}"
                await reply_line_message(reply_token, reply_msg)

            # 3. ปุ่มดูแนวรับ-แนวต้านประจำวัน
            elif user_text in ["แนวรับแนวต้าน", "pivot", "แนวรับ", "แนวต้าน"]:
                pivots = get_daily_pivots()
                if pivots:
                    reply_msg = (
                        f"🎯 กรอบแนวรับ-แนวต้าน วันนี้ (XAU/USD)\n"
                        f"═════════════════\n"
                        f"💵 ราคาปัจจุบัน: {pivots['current_price']:.2f}\n"
                        f"📊 กรอบเมื่อวาน: High {pivots['prev_high']:.2f} | Low {pivots['prev_low']:.2f}\n"
                        f"═════════════════\n"
                        f"🔴 ต้าน 3 (R3): {pivots['r3']:.2f}\n"
                        f"🔴 ต้าน 2 (R2): {pivots['r2']:.2f}\n"
                        f"🔴 ต้าน 1 (R1): {pivots['r1']:.2f}\n"
                        f"⚖️ Pivot กลาง: {pivots['pivot']:.2f}\n"
                        f"🟢 รับ 1 (S1): {pivots['s1']:.2f}\n"
                        f"🟢 รับ 2 (S2): {pivots['s2']:.2f}\n"
                        f"🟢 รับ 3 (S3): {pivots['s3']:.2f}\n"
                        f"═════════════════\n"
                        f"🕒 เวลาไทย: {get_thai_time()}"
                    )
                else:
                    reply_msg = "❌ ไม่สามารถดึงข้อมูลแนวรับ-แนวต้านได้ในขณะนี้"
                await reply_line_message(reply_token, reply_msg)

            # 4. ปุ่มดูบทวิเคราะห์ Multi-Timeframe
            elif user_text in ["วิเคราะห์เช้า", "วิเคราะห์", "ภาพรวม"]:
                try:
                    trend_1h, rsi_1h, _ = get_tf_trend('1h')
                    trend_4h, rsi_4h, _ = get_tf_trend('4h')
                    trend_1d, rsi_1d, _ = get_tf_trend('1d')
                    trend_1w, rsi_1w, _ = get_tf_trend('1w')
                    trend_1m, rsi_1m, _ = get_tf_trend('1M')

                    reply_msg = (
                        f"📊 โครงสร้างแนวโน้ม Multi-Timeframe\n"
                        f"═════════════════\n"
                        f"• TF 1H  : {trend_1h} (RSI: {rsi_1h:.1f})\n"
                        f"• TF 4H  : {trend_4h} (RSI: {rsi_4h:.1f})\n"
                        f"• TF Day : {trend_1d} (RSI: {rsi_1d:.1f})\n"
                        f"• TF Week: {trend_1w} (RSI: {rsi_1w:.1f})\n"
                        f"• TF Month: {trend_1m} (RSI: {rsi_1m:.1f})\n"
                        f"═════════════════\n"
                        f"🕒 เวลาไทย: {get_thai_time()}"
                    )
                except Exception as e:
                    reply_msg = f"❌ เกิดข้อผิดพลาด: {e}"
                await reply_line_message(reply_token, reply_msg)

            # อื่นๆ
            else:
                help_msg = (
                    f"🤖 เมนูกดสั่งการบอท XAUUSD\n"
                    f"═════════════════\n"
                    f"• พิมพ์ 'ราคา' : เช็คราคาปัจจุบัน\n"
                    f"• พิมพ์ 'สถานะ' : เช็คเทรนด์ & RSI\n"
                    f"• พิมพ์ 'แนวรับแนวต้าน' : ดูจุด Pivot R1-R3 / S1-S3\n"
                    f"• พิมพ์ 'วิเคราะห์' : ดูเทรนด์ 1H ถึง Month"
                )
                await reply_line_message(reply_token, help_msg)

    return {"status": "ok"}
    
@app.api_route("/", methods=["GET", "HEAD"])
def health_check():
    return {"status": "running", "bot": "XAUUSD Signal Scanner"}

@app.get("/test-line")
async def test_line():
    current_time_th = get_thai_time('%H:%M:%S')
    try:
        df = fetch_gold_data()
        latest_bar = df.iloc[-1]
        current_price = float(latest_bar['close'])
        
        test_msg = (
            f"🔔 [TEST] ระบบแจ้งเตือน XAUUSD\n"
            f"═════════════════\n"
            f"💰 ราคาทองคำปัจจุบัน: {current_price:.2f}\n"
            f"🕒 เวลาไทย: {current_time_th}"
            f"═════════════════\n"
            f"✅ บอททำงานปกติบน Render"
        )
        await send_line_message(test_msg)
        return {"status": "Success", "current_price": current_price}
    except Exception as e:
        error_msg = f"Error fetching test price: {e}"
        print(error_msg)
        await send_line_message(f"🔔 [TEST] บอททำงานปกติ (ไม่สามารถดึงราคาได้: {e})")
        return {"status": "Error", "message": str(e)}

@app.get("/test-morning")
async def test_morning():
    await send_morning_briefing()
    return {"status": "Morning briefing test triggered"}
