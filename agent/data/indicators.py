"""Technical indicator calculations using the ta library.

Calculates RSI, MACD, moving averages, and other indicators from bar data.
"""

from decimal import Decimal

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import AverageTrueRange

from agent.data.streaming import BarData


class IndicatorCalculator:
    """
    Calculate technical indicators from bar data.

    Uses the ta library for indicator calculations.
    Requires a minimum number of bars to produce valid results.
    """

    # Minimum bars required for each indicator
    MIN_BARS_RSI = 14
    MIN_BARS_MACD = 26
    MIN_BARS_MA50 = 50
    MIN_BARS_MA200 = 200
    MIN_BARS_ATR = 14

    @staticmethod
    def calculate_all(bars: list[BarData]) -> dict:
        """
        Calculate all indicators from a list of bars.

        Args:
            bars: List of BarData objects, oldest first

        Returns:
            Dictionary with indicator values (None if insufficient data)
        """
        if not bars or len(bars) < 2:
            return {
                "rsi": None,
                "macd": None,
                "macd_signal": None,
                "ma_50": None,
                "ma_200": None,
                "atr": None,
                "adx": None,
            }

        # Convert bars to pandas DataFrame
        df = IndicatorCalculator._bars_to_dataframe(bars)

        # Calculate each indicator
        rsi = IndicatorCalculator._calculate_rsi(df)
        macd, macd_signal = IndicatorCalculator._calculate_macd(df)
        ma_50 = IndicatorCalculator._calculate_sma(df, 50)
        ma_200 = IndicatorCalculator._calculate_sma(df, 200)
        atr = IndicatorCalculator._calculate_atr(df)

        return {
            "rsi": rsi,
            "macd": macd,
            "macd_signal": macd_signal,
            "ma_50": Decimal(str(ma_50)) if ma_50 is not None else None,
            "ma_200": Decimal(str(ma_200)) if ma_200 is not None else None,
            "atr": atr,
            "adx": None,  # ADX requires more complex calculation, skip for now
        }

    @staticmethod
    def _bars_to_dataframe(bars: list[BarData]) -> pd.DataFrame:
        """Convert list of BarData to pandas DataFrame."""
        data = {
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [b.volume for b in bars],
        }
        return pd.DataFrame(data)

    @staticmethod
    def _calculate_rsi(df: pd.DataFrame, period: int = 14) -> float | None:
        """
        Calculate RSI (Relative Strength Index).

        Args:
            df: DataFrame with 'close' column
            period: RSI period (default 14)

        Returns:
            Current RSI value or None if insufficient data
        """
        if len(df) < period:
            return None

        try:
            rsi = RSIIndicator(close=df["close"], window=period)
            rsi_values = rsi.rsi()

            # Get the last non-NaN value
            last_valid = rsi_values.dropna()
            if len(last_valid) > 0:
                return round(float(last_valid.iloc[-1]), 2)
            return None
        except Exception:
            return None

    @staticmethod
    def _calculate_macd(
        df: pd.DataFrame,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> tuple[float | None, float | None]:
        """
        Calculate MACD and Signal line.

        Args:
            df: DataFrame with 'close' column
            fast: Fast EMA period (default 12)
            slow: Slow EMA period (default 26)
            signal: Signal line period (default 9)

        Returns:
            Tuple of (MACD value, Signal value) or (None, None)
        """
        if len(df) < slow:
            return None, None

        try:
            macd = MACD(
                close=df["close"],
                window_fast=fast,
                window_slow=slow,
                window_sign=signal,
            )

            macd_line = macd.macd()
            signal_line = macd.macd_signal()

            # Get last valid values
            macd_valid = macd_line.dropna()
            signal_valid = signal_line.dropna()

            macd_value = round(float(macd_valid.iloc[-1]), 4) if len(macd_valid) > 0 else None
            signal_value = round(float(signal_valid.iloc[-1]), 4) if len(signal_valid) > 0 else None

            return macd_value, signal_value
        except Exception:
            return None, None

    @staticmethod
    def _calculate_sma(df: pd.DataFrame, period: int) -> float | None:
        """
        Calculate Simple Moving Average.

        Args:
            df: DataFrame with 'close' column
            period: SMA period

        Returns:
            Current SMA value or None if insufficient data
        """
        if len(df) < period:
            return None

        try:
            sma = SMAIndicator(close=df["close"], window=period)
            sma_values = sma.sma_indicator()

            last_valid = sma_values.dropna()
            if len(last_valid) > 0:
                return round(float(last_valid.iloc[-1]), 2)
            return None
        except Exception:
            return None

    @staticmethod
    def _calculate_atr(df: pd.DataFrame, period: int = 14) -> float | None:
        """
        Calculate Average True Range.

        Args:
            df: DataFrame with 'high', 'low', 'close' columns
            period: ATR period (default 14)

        Returns:
            Current ATR value or None if insufficient data
        """
        if len(df) < period:
            return None

        try:
            atr = AverageTrueRange(
                high=df["high"],
                low=df["low"],
                close=df["close"],
                window=period,
            )
            atr_values = atr.average_true_range()

            last_valid = atr_values.dropna()
            if len(last_valid) > 0:
                return round(float(last_valid.iloc[-1]), 4)
            return None
        except Exception:
            return None
