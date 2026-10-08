import os
import math
import datetime
import requests
import pandas as pd
import numpy as np

# ==========================================
# 1. การตั้งค่าระบบ (SETTINGS & PARAMETERS)
# ==========================================
SYMBOL = "XAUUSD"
TIMEFRAME = "15m"

# Strategy Parameters
HMA_PERIOD = 25
RSI_PERIOD = 14
ATR_PERIOD = 14
REQUIRE_REJECTION = False      # กรองแท่งเทียนทิ้งไส้ (True/False)
WICK_TO_BODY_RATIO = 1.5       # อัตราส่วนความยาวไส้ต่อเนื้อเทียน

# Multi-Targets & Risk (ATR Multipliers)
ATR_SL_MULT = 1.5
ATR_TP1_MULT = 2.0
ATR_TP2_MULT = 3.2              # Main TP
ATR_TP3_MULT = 5.0              # Runner TP
ATR_TRAIL_ACT_MULT = 2.0        # จุดเริ่มเปิด Trailing Stop
ATR_TRAIL_DIST_MULT = 1.5       # ระยะ Trailing Stop หลังราคา

# Account Risk Parameters
ACCOUNT_EQUITY = 10000.0        # ยอดเงินทุนในพอร์ต ($)
RISK_PERCENT = 0.3              # ความเสี่ยงต่อไม้ 0.3%
POINT_VALUE_PER_LOT = 100.0     # ขนาด 1 Standard Lot ของทองคำ (100 oz)

# Time Filter (Bangkok UTC+7)
USE_TIME_FILTER = True
CUTOFF_HOUR_THAI = 19           # หยุดเปิดออเดอร์หลัง 19:00 น.

# Webhook / Notification Tokens
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
LINE_NOTIFY_TOKEN = os.getenv("LINE_NOTIFY_TOKEN", "")


# ==========================================
# 2. ฟังก์ชันคำนวณทางเทคนิค (INDICATORS)
# ==========================================
def calculate_wma(series: pd.Series, period: int) -> pd.Series:
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(lambda prices: np.dot(prices, weights) / weights.sum(), raw=True)

def calculate_hma(series: pd.Series, period: int) -> pd.Series:
    half_length = int(period / 2)
    sqrt_length = int(math.sqrt(period))
    wma_half = calculate_wma(series, half_length)
    wma_full = calculate_wma(series, period)
    diff = 2 * wma_half - wma_full
    return calculate_wma(diff, sqrt_length)

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


# ==========================================
# 3. ฟังก์ชันคำนวณความเสี่ยงและขนาดไม้ (DYNAMIC RISK)
# ==========================================
def calculate_dynamic_lot(equity: float, risk_pct: float, sl_distance: float) -> float:
    if sl_distance <= 0:
        return 0.01
    risk_amount = equity * (risk_pct / 100.0)
    loss_per_lot = sl_distance * POINT_VALUE_PER_LOT
    lot_size = risk_amount / loss_per_lot
    # ปัดเศษทศนิยม 2 ตำแหน่ง และคุมขั้นต่ำ 0.01 lot
    return max(0.01, round(math.floor(lot_size * 100) / 100, 2))


# ==========================================
# 4. ฟังก์ชันตรวจสอบเงื่อนไขเวลาและแจ้งเตือน
# ==========================================
def is_safe_trading_time() -> bool:
    if not USE_TIME_FILTER:
        return True
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    thai_time = now_utc + datetime.timedelta(hours=7)
    return thai_time.hour < CUTOFF_HOUR_THAI

def send_alert(message: str):
    print(f"\n[ALERT NOTIFICATION]\n{message}\n")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=5)
        except Exception as e:
            print(f"Telegram error: {e}")
            
    if LINE_NOTIFY_TOKEN:
        try:
            url = "https://notify-api.line.me/api/notify"
            headers = {"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"}
            requests.post(url, headers=headers, data={"message": message}, timeout=5)
        except Exception as e:
            print(f"LINE Notify error: {e}")


# ==========================================
# 5. ฟังก์ชันวิเคราะห์สัญญาณ (SIGNAL ENGINE)
# ==========================================
def analyze_market(df: pd.DataFrame):
    """
    df ต้องมีคอลัมน์: ['open', 'high', 'low', 'close'] เรียงจากอดีตไปปัจจุบัน
    """
    if len(df) < HMA_PERIOD + 20:
        print("Data insufficient for calculation.")
        return

    # คำนวณอินดิเคเตอร์
    df['hma'] = calculate_hma(df['close'], HMA_PERIOD)
    df['rsi'] = calculate_rsi(df['close'], RSI_PERIOD)
    df['atr'] = calculate_atr(df, ATR_PERIOD)

    # ดึงค่าแท่งก่อนหน้า (แท่งที่ปิดสมบูรณ์แล้วล่าสุด Index -1 และ -2)
    curr = df.iloc[-1]
    prev = df.iloc[-2]

    hma_curr = curr['hma']
    hma_prev = prev['hma']
    rsi_curr = curr['rsi']
    atr_curr = curr['atr']
    close_curr = curr['close']
    close_prev = prev['close']
    open_curr = curr['open']
    high_curr = curr['high']
    low_curr = curr['low']

    # ทิศทาง HMA
    hma_up = hma_curr > hma_prev
    hma_down = hma_curr < hma_prev

    # Crossover ระหว่างราคาปิดและเส้น HMA
    buy_cross = (close_prev <= hma_prev) and (close_curr > hma_curr)
    sell_cross = (close_prev >= hma_prev) and (close_curr < hma_curr)

    # ตรรกะตรวจจับแท่งเทียนทิ้งไส้ (Price Rejection)
    body_size = abs(close_curr - open_curr)
    if body_size == 0:
        body_size = 0.01
    lower_wick = min(open_curr, close_curr) - low_curr
    upper_wick = high_curr - max(open_curr, close_curr)

    valid_rejection_buy = True
    valid_rejection_sell = True
    if REQUIRE_REJECTION:
        valid_rejection_buy = (lower_wick >= body_size * WICK_TO_BODY_RATIO) and (lower_wick > upper_wick)
        valid_rejection_sell = (upper_wick >= body_size * WICK_TO_BODY_RATIO) and (upper_wick > lower_wick)

    # เงื่อนไขรวม
    buy_signal = buy_cross and hma_up and (rsi_curr > 50.0) and valid_rejection_buy
    sell_signal = sell_cross and hma_down and (rsi_curr < 50.0) and valid_rejection_sell

    # ตรวจสอบช่วงเวลาเทรด
    if not is_safe_trading_time():
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Market Scan: Outside safe trading hours (Past 19:00 TH). No new entries.")
        return

    # ประมวลผลเมื่อเกิดสัญญาณ
    if buy_signal:
        sl_dist = atr_curr * ATR_SL_MULT
        sl_price = round(close_curr - sl_dist, 2)
        tp1_price = round(close_curr + (atr_curr * ATR_TP1_MULT), 2)
        tp2_price = round(close_curr + (atr_curr * ATR_TP2_MULT), 2)
        tp3_price = round(close_curr + (atr_curr * ATR_TP3_MULT), 2)
        lot_size = calculate_dynamic_lot(ACCOUNT_EQUITY, RISK_PERCENT, sl_dist)

        msg = (
            f"🟢 [LIGHT BUY SIGNAL] {SYMBOL} ({TIMEFRAME})\n"
            f"-----------------------------------\n"
            f"• Entry Price : {close_curr:.2f}\n"
            f"• Calculated Lot: {lot_size} (Risk {RISK_PERCENT}%)\n"
            f"• Stop Loss   : {sl_price:.2f} (-{sl_dist:.2f})\n"
            f"• TP
