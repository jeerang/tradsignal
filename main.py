import os
import sys
import logging
from datetime import datetime
import pandas as pd
import numpy as np
import yfinance as yf
from dotenv import load_dotenv

# Ensure UTF-8 output encoding for Windows command line terminals
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("XAUUSD_Signal")


class XAUUSDSignalBot:
    """Lightweight Trading Signal Generator for XAUUSD (Gold)."""

    def __init__(self, symbol: str = "GC=F", interval: str = "1h", period: str = "1mo"):
        self.symbol = os.getenv("SYMBOL", symbol)
        self.interval = interval
        self.period = period
        self.ema_fast_period = int(os.getenv("EMA_FAST", 9))
        self.ema_slow_period = int(os.getenv("EMA_SLOW", 21))
        self.rsi_period = int(os.getenv("RSI_PERIOD", 14))

    def fetch_data(self) -> pd.DataFrame:
        """Fetch market data from Yahoo Finance."""
        logger.info(f"Fetching data for {self.symbol} (Interval: {self.interval}, Period: {self.period})...")
        ticker = yf.Ticker(self.symbol)
        df = ticker.history(period=self.period, interval=self.interval)
        
        if df.empty:
            # Fallback to XAUUSD=X if GC=F yields no data
            logger.warning(f"No data found for {self.symbol}, trying fallback XAUUSD=X...")
            ticker = yf.Ticker("XAUUSD=X")
            df = ticker.history(period=self.period, interval=self.interval)
            
        if df.empty:
            raise ValueError("Failed to fetch XAUUSD data from market data provider.")

        return df

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators (EMA, RSI, ATR)."""
        df = df.copy()
        
        # Calculate EMA
        df["EMA_Fast"] = df["Close"].ewm(span=self.ema_fast_period, adjust=False).mean()
        df["EMA_Slow"] = df["Close"].ewm(span=self.ema_slow_period, adjust=False).mean()
        
        # Calculate RSI
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / (loss + 1e-10)
        df["RSI"] = 100 - (100 / (1 + rs))

        # Calculate ATR (Average True Range) for Stop Loss & Take Profit positioning
        high_low = df["High"] - df["Low"]
        high_close = np.abs(df["High"] - df["Close"].shift())
        low_close = np.abs(df["Low"] - df["Close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df["ATR"] = true_range.rolling(14).mean()

        return df

    def generate_signal(self, df: pd.DataFrame) -> dict:
        """Generate BUY, SELL, or HOLD signal based on latest indicator values."""
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

        # Bullish Crossover (EMA Fast crosses above EMA Slow)
        bullish_cross = (prev_ema_fast <= prev_ema_slow) and (ema_fast > ema_slow)
        # Bearish Crossover (EMA Fast crosses below EMA Slow)
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
        elif ema_fast > ema_slow and rsi < 30:
            signal = "BUY"
            reason = f"Oversold condition in Uptrend (RSI={rsi:.1f})"
            sl = round(price - (atr * 1.5), 2)
            tp = round(price + (atr * 2.0), 2)
        elif ema_fast < ema_slow and rsi > 70:
            signal = "SELL"
            reason = f"Overbought condition in Downtrend (RSI={rsi:.1f})"
            sl = round(price + (atr * 1.5), 2)
            tp = round(price - (atr * 2.0), 2)

        timestamp = df.index[-1].strftime("%Y-%m-%d %H:%M:%S")

        return {
            "timestamp": timestamp,
            "symbol": self.symbol,
            "price": round(price, 2),
            "signal": signal,
            "reason": reason,
            "ema_fast": round(ema_fast, 2),
            "ema_slow": round(ema_slow, 2),
            "rsi": round(rsi, 1),
            "stop_loss": sl,
            "take_profit": tp
        }

    def run(self):
        """Run analysis pipeline and print report."""
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

            return result
        except Exception as e:
            logger.error(f"Error running signal bot: {e}")
            raise

if __name__ == "__main__":
    bot = XAUUSDSignalBot()
    bot.run()
