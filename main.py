import os
import time
import httpx
import ccxt
import pandas as pd
import pandas_ta as ta
from apscheduler.schedulers.blocking import BlockingScheduler

LINE_ACCESS_TOKEN = os.getenv("fbL8B+e8voao+f41Nx5DC9pT1GtsmwhlAQTN+rPFaNLQqPWCo7KyJmNNFMMAjIgc62xMfG4YQs/fzLjjTZTGF31q5+OshzTzI34aOw5KzLt2UFcm9LEi7KwgH5yZ4V6zjkudUdjEwCyxYQt6HELdBQdB04t89/1O/w1cDnyilFU=")
LINE_USER_ID = os.getenv("U4776c4283302343cebd85ab4cefbf2f9")

exchange = ccxt.binance()
symbol = "PAXG/USDT"  # ทองคำ Gold Spot บน Binance (1 PAXG = 1 troy oz Gold)
timeframe = "1m"

last_signal = None

def send_line_message(text: str):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    body = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text}]
    }
    try:
        with httpx.Client() as client:
            client.post("https://api.line.me/v2/bot/message/push", headers=headers, json=body)
    except Exception as e:
        print(f"Error sending LINE message: {e}")

def check_signal():
    global last_signal
    try:
        # ดึงข้อมูลแท่งเทียน 100 แท่งล่าสุด
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
        
        # คำนวณ RSI (Period 14)
        df['rsi'] = ta.rsi(df['close'], length=14)
        
        # คำนวณ Supertrend (Period 7, Multiplier 1.2)
        st_data = ta.supertrend(df['high'], df['low'], df['close'], length=7, multiplier=1.2)
        df['st_direction'] = st_data['SUPERTd_7_1.2']  # 1 = ขาขึ้น (BUY), -1 = ขาลง (SELL)
        
        # ดึงค่าของแท่งเทียนที่เพิ่งปิดสมบูรณ์ (แท่งรองสุดท้าย index -2)
        closed_bar = df.iloc[-2]
        prev_bar = df.iloc[-3]
        
        close_price = closed_bar['close']
        rsi_val = closed_bar['rsi']
        current_dir = closed_bar['st_direction']
        prev_dir = prev_bar['st_direction']
        
        # ตรวจสอบเงื่อนไขตัดข้าม (Cross)
        if prev_dir == -1 and current_dir == 1 and rsi_val > 50:
            if last_signal != "BUY":
                last_signal = "BUY"
                msg = f"🟢 BUY Signal XAUUSD\nEntry: {close_price:.2f}\nRSI: {rsi_val:.1f}\nTF: 1m"
                send_line_message(msg)
                print("BUY Signal Sent!")
                
        elif prev_dir == 1 and current_dir == -1 and rsi_val < 50:
            if last_signal != "SELL":
                last_signal = "SELL"
                msg = f"🔴 SELL Signal XAUUSD\nEntry: {close_price:.2f}\nRSI: {rsi_val:.1f}\nTF: 1m"
                send_line_message(msg)
                print("SELL Signal Sent!")
                
    except Exception as e:
        print(f"Check error: {e}")

if __name__ == "__main__":
    print("🚀 Bot Started - Checking Gold Signals every minute...")
    scheduler = BlockingScheduler()
    # รันตรวจสอบทุกๆ นาที
    scheduler.add_job(check_signal, 'cron', second='5')
    scheduler.start()
