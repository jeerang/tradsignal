import os
import sys
import logging
from datetime import datetime
import pytz
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from dotenv import load_dotenv

# Ensure UTF-8 output encoding for Windows command line terminals
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Load environment variables if .env exists
load_dotenv()

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("XAUUSD_Signal")

# Configuration & Constants requested
LINE_CHANNEL_ACCESS_TOKEN = os.getenv(
    "LINE_CHANNEL_ACCESS_TOKEN",
    "KvNZvrpSbwGYFBu76Y8ximlw/LnKmoDTisOFzkyCoFo8T/REVrytbOCjJdo+tYu662xMfG4YQs/fzLjjTZTGF31q5+OshzTzI34aOw5KzLsuXYdExswTFruj/lzfLQudFbK3Dh66t9YpP4hT7HHVXAdB04t89/1O/w1cDnyilFU="
)
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "12d9362f07b746e885d8f5a87712a35d")
LINE_USER_ID = os.getenv("LINE_USER_ID", "U4776c4283302343cebd85ab4cefbf2f9")
APP_URL = os.getenv("RENDER_EXTERNAL_URL", "https://tradsignal.onrender.com")

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")
SCALPING_MODE = True

def get_thai_time() -> str:
    """Return formatted current time in Bangkok Timezone."""
    return datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d %H:%M:%S")

def send_line_notification(message: str) -> bool:
    """Send LINE push message using LINE Messaging API."""
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        logger.warning("LINE notification skipped: Missing Channel Access Token or User ID.")
        return False

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            logger.info("LINE push notification sent successfully!")
            return True
        else:
            logger.error(f"Failed to send LINE notification: Status {res.status_code} - {res.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending LINE notification: {e}")
        return False

class XAUUSDSignalBot:
    """Lightweight Trading Signal Generator for XAUUSD (Gold)."""

    def __init__(self, symbol: str = "XAU/USD", interval: str = "1h"):
        self.symbol = symbol
        self.interval = interval
        self.ema_fast_period = int(os.getenv("EMA_FAST", 9))
        self.ema_slow_period = int(os.getenv("EMA_SLOW", 21))
        self.rsi_period = int(os.getenv("RSI_PERIOD", 14))

    def fetch_data(self) -> pd.DataFrame:
        """Fetch market data from Twelve Data API or yfinance fallback."""
        logger.info(f"Fetching data for {self.symbol}...")
        
        # Try Twelve Data API first
        if TWELVE_DATA_API_KEY:
            try:
                url = f"https://api.twelvedata.com/time_series?symbol={self.symbol}&interval={self.interval}&outputsize=50&apikey={TWELVE_DATA_API_KEY}"
                res = requests.get(url, timeout=10)
                data = res.json()
                if "values" in data and len(data["values"]) > 0:
                    df = pd.DataFrame(data["values"])
                    df["datetime"] = pd.to_datetime(df["datetime"])
                    df = df.sort_values("datetime").reset_index(drop=True)
                    for col in ["open", "high", "low", "close"]:
                        df[col] = df[col].astype(float)
                    df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"}, inplace=True)
                    df.set_index("datetime", inplace=True)
                    logger.info("Successfully fetched data from Twelve Data API.")
                    return df
            except Exception as e:
                logger.warning(f"Twelve Data API fetch failed: {e}. Falling back to Yahoo Finance...")

        # Fallback to Yahoo Finance
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period="1mo", interval=self.interval)
        if df.empty:
            ticker = yf.Ticker("XAUUSD=X")
            df = ticker.history(period="1mo", interval=self.interval)

        if df.empty:
            raise ValueError("Failed to fetch XAUUSD data from all market providers.")

        logger.info("Successfully fetched data from Yahoo Finance.")
        return df

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators (EMA, RSI, ATR)."""
        df = df.copy()
        
        df["EMA_Fast"] = df["Close"].ewm(span=self.ema_fast_period, adjust=False).mean()
        df["EMA_Slow"] = df["Close"].ewm(span=self.ema_slow_period, adjust=False).mean()
        
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / (loss + 1e-10)
        df["RSI"] = 100 - (100 / (1 + rs))

        high_low = df["High"] - df["Low"]
        high_close = np.abs(df["High"] - df["Close"].shift())
        low_close = np.abs(df["Low"] - df["Close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df["ATR"] = true_range.rolling(14).mean()

        return df

    def generate_signal(self, df: pd.DataFrame) -> dict:
        """Generate BUY, SELL, or HOLD signal."""
        if len(df) < 2:
            return {"signal": "HOLD", "reason": "Insufficient data"}

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        price = float(latest["Close"])
        ema_fast = float(latest["EMA_Fast"])
        ema_slow = float(latest["EMA_Slow"])
        rsi = float(latest["RSI"])
        atr = float(latest["ATR"]) if not np.isnan(latest["ATR"]) else 5.0

        prev_ema_fast = float(prev["EMA_Fast"])
        prev_ema_slow = float(prev["EMA_Slow"])

        bullish_cross = (prev_ema_fast <= prev_ema_slow) and (ema_fast > ema_slow)
        bearish_cross = (prev_ema_fast >= prev_ema_slow) and (ema_fast < ema_slow)

        signal = "HOLD"
        reason = "No trade signal detected"
        sl = None
        tp = None

        if bullish_cross and rsi > 45:
            signal = "BUY"
            reason = f"Bullish EMA Crossover ({self.ema_fast_period} > {self.ema_slow_period}) & RSI={rsi:.1f}"
            sl = round(price - (atr * 1.5), 2)
            tp = round(price + (atr * 2.5), 2)
        elif bearish_cross and rsi < 55:
            signal = "SELL"
            reason = f"Bearish EMA Crossover ({self.ema_fast_period} < {self.ema_slow_period}) & RSI={rsi:.1f}"
            sl = round(price + (atr * 1.5), 2)
            tp = round(price - (atr * 2.5), 2)
        elif ema_fast > ema_slow and rsi < 35:
            signal = "BUY"
            reason = f"Oversold condition in Uptrend (RSI={rsi:.1f})"
            sl = round(price - (atr * 1.5), 2)
            tp = round(price + (atr * 2.0), 2)
        elif ema_fast < ema_slow and rsi > 65:
            signal = "SELL"
            reason = f"Overbought condition in Downtrend (RSI={rsi:.1f})"
            sl = round(price + (atr * 1.5), 2)
            tp = round(price - (atr * 2.0), 2)

        timestamp_bkk = get_thai_time()

        return {
            "timestamp": timestamp_bkk,
            "symbol": "XAU/USD",
            "price": round(price, 2),
            "signal": signal,
            "reason": reason,
            "ema_fast": round(ema_fast, 2),
            "ema_slow": round(ema_slow, 2),
            "rsi": round(rsi, 1),
            "stop_loss": sl,
            "take_profit": tp
        }

    def run(self, notify_line: bool = True):
        """Run analysis pipeline, print report, and send LINE notification."""
        try:
            df = self.fetch_data()
            df = self.calculate_indicators(df)
            result = self.generate_signal(df)

            print("\n" + "="*50)
            print(f" [XAUUSD TRADING SIGNAL REPORT] - {result['timestamp']}")
            print("="*50)
            print(f" Symbol       : {result['symbol']}")
            print(f" Current Price: ${result['price']}")
            print(f" EMA ({self.ema_fast_period}/{self.ema_slow_period})   : {result['ema_fast']} / {result['ema_slow']}")
            print(f" RSI ({self.rsi_period})      : {result['rsi']}")
            print("-" * 50)
            
            sig = result['signal']
            color_code = "\033[92m" if sig == "BUY" else ("\033[91m" if sig == "SELL" else "\033[93m")
            reset_code = "\033[0m"

            print(f" SIGNAL       : {color_code}[ {sig} ]{reset_code}")
            print(f" Reason       : {result['reason']}")
            if sig != "HOLD":
                print(f" Stop Loss    : ${result['stop_loss']}")
                print(f" Take Profit  : ${result['take_profit']}")
            print("="*50 + "\n")

            # Formulate LINE notification message
            mode_status = "🟢 Active" if SCALPING_MODE else "🔴 Paused"
            sig_emoji = "🟢 BUY" if sig == "BUY" else ("🔴 SELL" if sig == "SELL" else "🟡 HOLD")
            
            line_msg = (
                f"📊 XAUUSD TRADING SIGNAL REPORT\n"
                f"═════════════════\n"
                f"💵 ราคาทองคำ: ${result['price']}\n"
                f"📈 EMA ({self.ema_fast_period}/{self.ema_slow_period}): {result['ema_fast']} / {result['ema_slow']}\n"
                f"📉 RSI ({self.rsi_period}): {result['rsi']}\n"
                f"═════════════════\n"
                f"🎯 สัญญาณ: {sig_emoji}\n"
                f"💡 เหตุผล: {result['reason']}\n"
            )
            
            if sig != "HOLD":
                line_msg += (
                    f"🛑 Stop Loss: ${result['stop_loss']}\n"
                    f"🎯 Take Profit: ${result['take_profit']}\n"
                )
                
            line_msg += (
                f"═════════════════\n"
                f"⚙️ Scalping Mode: {mode_status}\n"
                f"🕒 เวลา (Bangkok): {result['timestamp']}"
            )

            if notify_line:
                send_line_notification(line_msg)

            return result
        except Exception as e:
            logger.error(f"Error running signal bot: {e}")
            raise

if __name__ == "__main__":
    bot = XAUUSDSignalBot()
    bot.run()
