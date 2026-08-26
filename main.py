from dotenv import load_dotenv
load_dotenv()  

import yfinance as yf
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

def fetch_gold_data():
    # ใช้ "XAUUSD=X" ซึ่งเป็นราคา Gold Spot สากล (ตรงกับ FXCM/OANDA บน TradingView)
    gold = yf.Ticker("XAUUSD=X")
    df = gold.history(period="1d", interval="1m")
    
    # กรณีวันเสาร์-อาทิตย์ หรือช่วงตลาดปิด ถ้า 1m ไม่มีข้อมูล ให้สำรองด้วย 5m
    if df.empty:
        df = gold.history(period="5d", interval="5m")
        
    df = df.reset_index()
    df = df.rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "vol"
    })
    return df
exchange = ccxt.binance()
symbol = "PAXG/USDT"  # ทองคำ XAUUSDT บน Binance
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

        print(f"[{time.strftime('%H:%M:%S')}] Checked XAUUSD: Price={entry_price:.2f}, RSI={rsi_val:.1f}, Dir={curr_dir}")

        # สัญญาณ BUY
        if prev_dir == -1 and curr_dir == 1 and rsi_val > 50:
            if last_signal != "BUY":
                last_signal = "BUY"
                sl = float(closed_bar['supertrend'])  # SL ตามเส้น Supertrend ขาขึ้น
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
                    f"📊 RSI: {rsi_val:.1f} | ATR: {atr_val:.2f}"
                )
                await send_line_message(msg)

        # สัญญาณ SELL
        elif prev_dir == 1 and curr_dir == -1 and rsi_val < 50:
            if last_signal != "SELL":
                last_signal = "SELL"
                sl = float(closed_bar['supertrend'])  # SL ตามเส้น Supertrend ขาลง
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
                    f"📊 RSI: {rsi_val:.1f} | ATR: {atr_val:.2f}"
                )
                await send_line_message(msg)

    except Exception as e:
        print(f"Check error: {e}")
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_signal, 'cron', second='5')
    scheduler.start()
    print("🚀 Background Signal Scanner Started!")
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
def health_check():
    return {"status": "running", "bot": "XAUUSD Signal Scanner"}

@app.get("/test-line")
async def test_line():
    try:
        df = fetch_gold_data()
        latest_bar = df.iloc[-1]
        current_price = float(latest_bar['close'])
        
        test_msg = (
            f"🔔 [TEST] ระบบแจ้งเตือน XAUUSD\n"
            f"═════════════════\n"
            f"💰 ราคาทองคำปัจจุบัน: {current_price:.2f}\n"
            f"🕒 เวลา: {time.strftime('%H:%M:%S')}\n"
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
