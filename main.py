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

LINE_ACCESS_TOKEN = os.getenv("KvNZvrpSbwGYFBu76Y8ximlw/LnKmoDTisOFzkyCoFo8T/REVrytbOCjJdo+tYu662xMfG4YQs/fzLjjTZTGF31q5+OshzTzI34aOw5KzLsuXYdExswTFruj/lzfLQudFbK3Dh66t9YpP4hT7HHVXAdB04t89/1O/w1cDnyilFU=")
LINE_USER_ID = os.getenv("U4776c4283302343cebd85ab4cefbf2f9")

exchange = ccxt.binance()
symbol = "PAXG/USDT"  # ทองคำ Gold Spot
timeframe = "1m"
last_signal = None

async def send_line_message(text: str):
    if not LINE_ACCESS_TOKEN or not LINE_USER_ID:
        print("Missing LINE credentials in Environment Variables")
        return
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
            print(f"LINE Notification Sent, status: {res.status_code}")
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

    df['supertrend'] = supertrend
    df['direction'] = direction
    return df

async def check_signal():
    global last_signal
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'vol'])

        df['rsi'] = calculate_rsi(df['close'], period=14)
        df = calculate_supertrend(df, period=7, multiplier=1.2)

        closed_bar = df.iloc[-2]
        prev_bar = df.iloc[-3]

        close_price = closed_bar['close']
        rsi_val = closed_bar['rsi']
        curr_dir = closed_bar['direction']
        prev_dir = prev_bar['direction']

        print(f"[{time.strftime('%H:%M:%S')}] Checked: Price={close_price:.2f}, RSI={rsi_val:.1f}, Dir={curr_dir}")

        if prev_dir == -1 and curr_dir == 1 and rsi_val > 50:
            if last_signal != "BUY":
                last_signal = "BUY"
                msg = f"🟢 BUY Signal XAUUSD\nEntry: {close_price:.2f}\nRSI: {rsi_val:.1f}\nTF: 1m"
                await send_line_message(msg)

        elif prev_dir == 1 and curr_dir == -1 and rsi_val < 50:
            if last_signal != "SELL":
                last_signal = "SELL"
                msg = f"🔴 SELL Signal XAUUSD\nEntry: {close_price:.2f}\nRSI: {rsi_val:.1f}\nTF: 1m"
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
    await send_line_message("🔔 ทดสอบการแจ้งเตือนจากบอท XAUUSD บน Render!")
    return {"status": "Test message triggered"}

