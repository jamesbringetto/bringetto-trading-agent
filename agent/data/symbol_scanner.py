"""Dynamic symbol scanner for discovering tradeable US stocks.

Replaces the hardcoded SP500_ASSETS list with a runtime system that:
1. Queries Alpaca's asset API for all active, tradeable US equities
2. Screens for liquidity (price, volume) using recent historical bars
3. Provides strategy-specific sub-screens (gap scan, momentum scan)
4. Supports intraday rescans for dynamic symbol discovery

The scanner runs pre-market each day and produces a filtered universe
that gets fed to strategies and the data streamer.
"""

import time
from datetime import datetime, timedelta
from typing import Any

from alpaca.common.exceptions import APIError
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockSnapshotRequest,
)
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, AssetStatus
from alpaca.trading.requests import GetAssetsRequest
from loguru import logger

from agent.config.settings import get_settings

# Rate limit: Alpaca allows 200 requests/min.
# We batch bar requests at up to 100 symbols each to stay well within limits.
BARS_BATCH_SIZE = 100
# Pause between bar batches to respect rate limits
BATCH_DELAY_SECONDS = 0.5


class ScanResult:
    """Result of a symbol scan with categorized symbol lists."""

    def __init__(
        self,
        all_qualified: list[str],
        by_avg_volume: dict[str, float],
        by_last_close: dict[str, float],
        scan_time: datetime,
    ):
        self.all_qualified = all_qualified
        self.by_avg_volume = by_avg_volume
        self.by_last_close = by_last_close
        self.scan_time = scan_time

    @property
    def count(self) -> int:
        return len(self.all_qualified)

    def symbols_above_volume(self, min_volume: float) -> list[str]:
        """Get symbols with average volume above threshold."""
        return [s for s in self.all_qualified if self.by_avg_volume.get(s, 0) >= min_volume]

    def symbols_above_price(self, min_price: float) -> list[str]:
        """Get symbols with last close above threshold."""
        return [s for s in self.all_qualified if self.by_last_close.get(s, 0) >= min_price]

    def symbols_in_price_range(self, min_price: float, max_price: float) -> list[str]:
        """Get symbols with last close in a price range."""
        return [
            s for s in self.all_qualified if min_price <= self.by_last_close.get(s, 0) <= max_price
        ]


class SymbolScanner:
    """
    Discovers and filters tradeable US stock symbols dynamically.

    Uses Alpaca's asset API and historical data to build a daily
    universe of qualified symbols that meet liquidity and price criteria.
    """

    def __init__(self):
        settings = get_settings()
        self._trading_client = TradingClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            paper=settings.is_paper_trading,
        )
        self._data_client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
        )

        # Cache the latest scan result
        self._last_scan: ScanResult | None = None

        # Configuration from settings
        self._min_price = settings.scanner_min_price
        self._min_avg_volume = settings.scanner_min_avg_volume
        self._lookback_days = settings.scanner_lookback_days
        self._max_symbols = settings.scanner_max_symbols

        logger.info(
            f"SymbolScanner initialized - "
            f"min_price=${self._min_price}, "
            f"min_avg_volume={self._min_avg_volume:,}, "
            f"lookback={self._lookback_days}d, "
            f"max_symbols={self._max_symbols}"
        )

    @property
    def last_scan(self) -> ScanResult | None:
        """Get the most recent scan result."""
        return self._last_scan

    def get_qualified_symbols(self) -> list[str]:
        """Get currently qualified symbols, or empty list if no scan has run."""
        if self._last_scan is None:
            return []
        return self._last_scan.all_qualified

    def _fetch_active_assets(self) -> list[dict[str, Any]]:
        """
        Fetch all active, tradeable US equities from Alpaca.

        Returns a list of asset dicts with symbol, exchange, name, etc.
        This is a single API call — Alpaca returns all assets at once.
        """
        try:
            request = GetAssetsRequest(
                status=AssetStatus.ACTIVE,
                asset_class=AssetClass.US_EQUITY,
            )
            assets = self._trading_client.get_all_assets(request)

            # Filter for tradeable, non-OTC equities on major exchanges
            valid_exchanges = {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS", "NYSEARCA"}
            candidates = []
            for asset in assets:
                if (
                    asset.tradable
                    and asset.status == AssetStatus.ACTIVE
                    and asset.exchange in valid_exchanges
                    # Skip symbols with special characters (warrants, units, etc.)
                    and "." not in asset.symbol
                    and "/" not in asset.symbol
                    and "-" not in asset.symbol
                ):
                    candidates.append(
                        {
                            "symbol": asset.symbol,
                            "exchange": asset.exchange,
                            "name": asset.name,
                            "easy_to_borrow": getattr(asset, "easy_to_borrow", False),
                            "shortable": getattr(asset, "shortable", False),
                            "fractionable": getattr(asset, "fractionable", False),
                        }
                    )

            logger.info(
                f"Fetched {len(assets)} total assets, "
                f"{len(candidates)} candidates after exchange/tradability filter"
            )
            return candidates

        except APIError as e:
            logger.error(f"Failed to fetch assets from Alpaca: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching assets: {e}")
            return []

    def _screen_by_bars(
        self,
        symbols: list[str],
        min_price: float,
        min_avg_volume: float,
        lookback_days: int,
    ) -> tuple[list[str], dict[str, float], dict[str, float]]:
        """
        Screen symbols using recent historical daily bars.

        Fetches bars in batches to respect rate limits.
        Returns (qualified_symbols, volume_map, price_map).
        """
        qualified: list[str] = []
        volume_map: dict[str, float] = {}
        price_map: dict[str, float] = {}

        start_date = datetime.now() - timedelta(days=lookback_days + 5)  # Extra buffer for weekends

        total_batches = (len(symbols) + BARS_BATCH_SIZE - 1) // BARS_BATCH_SIZE
        logger.info(
            f"Screening {len(symbols)} symbols in {total_batches} batches "
            f"(min_price=${min_price}, min_avg_vol={min_avg_volume:,.0f})"
        )

        for batch_idx in range(0, len(symbols), BARS_BATCH_SIZE):
            batch = symbols[batch_idx : batch_idx + BARS_BATCH_SIZE]
            batch_num = batch_idx // BARS_BATCH_SIZE + 1

            try:
                request = StockBarsRequest(
                    symbol_or_symbols=batch,
                    timeframe=TimeFrame.Day,
                    start=start_date,
                )
                bars_response = self._data_client.get_stock_bars(request)

                for symbol in batch:
                    symbol_bars = bars_response.get(symbol, [])
                    if not symbol_bars or len(symbol_bars) < 2:
                        continue

                    # Calculate average volume over the lookback period
                    volumes = [b.volume for b in symbol_bars[-lookback_days:]]
                    avg_volume = sum(volumes) / len(volumes) if volumes else 0

                    # Get last close price
                    last_close = float(symbol_bars[-1].close)

                    if last_close >= min_price and avg_volume >= min_avg_volume:
                        qualified.append(symbol)
                        volume_map[symbol] = avg_volume
                        price_map[symbol] = last_close

                if batch_num < total_batches:
                    # Brief pause between batches to respect rate limits
                    time.sleep(BATCH_DELAY_SECONDS)

                if batch_num % 10 == 0 or batch_num == total_batches:
                    logger.info(
                        f"  Batch {batch_num}/{total_batches} complete - "
                        f"{len(qualified)} qualified so far"
                    )

            except APIError as e:
                logger.warning(f"API error on batch {batch_num}: {e}")
                # Continue with next batch rather than failing entirely
                time.sleep(2.0)
            except Exception as e:
                logger.error(f"Unexpected error on batch {batch_num}: {e}")
                time.sleep(2.0)

        logger.info(
            f"Screening complete: {len(qualified)} symbols qualified "
            f"out of {len(symbols)} candidates"
        )
        return qualified, volume_map, price_map

    def scan(self) -> ScanResult:
        """
        Run a full symbol scan: fetch assets, screen by liquidity.

        This is the primary method to call pre-market each day.
        Results are cached in self._last_scan.

        Returns:
            ScanResult with all qualified symbols and their metrics.
        """
        logger.info("Starting full symbol scan...")
        scan_start = datetime.now()

        # Step 1: Fetch all active, tradeable US equities
        assets = self._fetch_active_assets()
        if not assets:
            logger.warning("No assets fetched — scan aborted, using cached results")
            if self._last_scan:
                return self._last_scan
            return ScanResult(
                all_qualified=[],
                by_avg_volume={},
                by_last_close={},
                scan_time=scan_start,
            )

        symbols = [a["symbol"] for a in assets]

        # Step 2: Screen by price and volume using historical bars
        qualified, volume_map, price_map = self._screen_by_bars(
            symbols=symbols,
            min_price=self._min_price,
            min_avg_volume=self._min_avg_volume,
            lookback_days=self._lookback_days,
        )

        # Step 3: Cap at max_symbols, sorted by volume (most liquid first)
        if len(qualified) > self._max_symbols:
            qualified.sort(key=lambda s: volume_map.get(s, 0), reverse=True)
            qualified = qualified[: self._max_symbols]
            logger.info(f"Capped to top {self._max_symbols} symbols by volume")

        scan_duration = (datetime.now() - scan_start).total_seconds()
        result = ScanResult(
            all_qualified=qualified,
            by_avg_volume=volume_map,
            by_last_close=price_map,
            scan_time=scan_start,
        )
        self._last_scan = result

        logger.info(
            f"Symbol scan complete in {scan_duration:.1f}s — {result.count} qualified symbols"
        )

        # Log top symbols by volume for visibility
        top_by_vol = sorted(qualified, key=lambda s: volume_map.get(s, 0), reverse=True)[:20]
        logger.info(f"Top 20 by volume: {top_by_vol}")

        return result

    def scan_premarket_gaps(
        self,
        min_gap_pct: float = 3.0,
        min_price: float = 10.0,
        min_volume: float = 500_000,
    ) -> list[dict[str, Any]]:
        """
        Scan for pre-market gap candidates.

        Uses snapshot data to find symbols with significant overnight gaps.
        Intended to run around 9:25 AM ET before market open.

        Returns list of dicts with symbol, gap_pct, previous_close, current_price.
        """
        if self._last_scan is None:
            logger.warning("No prior scan available for gap screening")
            return []

        # Use the qualified universe from the daily scan
        symbols = self._last_scan.all_qualified
        gap_candidates: list[dict[str, Any]] = []

        logger.info(f"Scanning {len(symbols)} symbols for pre-market gaps >= {min_gap_pct}%")

        # Fetch snapshots in batches
        for batch_idx in range(0, len(symbols), BARS_BATCH_SIZE):
            batch = symbols[batch_idx : batch_idx + BARS_BATCH_SIZE]
            try:
                request = StockSnapshotRequest(symbol_or_symbols=batch)
                snapshots = self._data_client.get_stock_snapshot(request)

                for symbol, snapshot in snapshots.items():
                    if not snapshot or not snapshot.daily_bar or not snapshot.previous_daily_bar:
                        continue

                    prev_close = float(snapshot.previous_daily_bar.close)
                    current_price = float(snapshot.daily_bar.close)

                    if prev_close <= 0 or current_price < min_price:
                        continue

                    gap_pct = ((current_price - prev_close) / prev_close) * 100

                    if abs(gap_pct) >= min_gap_pct:
                        gap_candidates.append(
                            {
                                "symbol": symbol,
                                "gap_pct": round(gap_pct, 2),
                                "previous_close": prev_close,
                                "current_price": current_price,
                                "direction": "up" if gap_pct > 0 else "down",
                            }
                        )

                time.sleep(BATCH_DELAY_SECONDS)

            except APIError as e:
                logger.warning(f"API error during gap scan: {e}")
                time.sleep(2.0)
            except Exception as e:
                logger.error(f"Error during gap scan: {e}")

        # Sort by absolute gap size (largest first)
        gap_candidates.sort(key=lambda x: abs(x["gap_pct"]), reverse=True)

        logger.info(f"Found {len(gap_candidates)} gap candidates >= {min_gap_pct}%")
        for g in gap_candidates[:10]:
            logger.info(
                f"  Gap: {g['symbol']} {g['direction']} {g['gap_pct']:+.1f}% "
                f"(prev ${g['previous_close']:.2f} -> ${g['current_price']:.2f})"
            )

        return gap_candidates

    def scan_momentum_candidates(
        self,
        min_price: float = 10.0,
        min_volume: float = 2_000_000,
        min_return_pct: float = 2.0,
        lookback_days: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Scan for momentum candidates based on recent returns.

        Finds symbols with strong recent price movement and high volume.
        Can run intraday to discover new momentum plays.

        Returns list of dicts with symbol, return_pct, avg_volume, last_close.
        """
        if self._last_scan is None:
            logger.warning("No prior scan available for momentum screening")
            return []

        # Filter to higher-volume symbols for momentum
        candidates = [
            s
            for s in self._last_scan.all_qualified
            if self._last_scan.by_avg_volume.get(s, 0) >= min_volume
            and self._last_scan.by_last_close.get(s, 0) >= min_price
        ]

        momentum_candidates: list[dict[str, Any]] = []

        start_date = datetime.now() - timedelta(days=lookback_days + 5)

        logger.info(
            f"Scanning {len(candidates)} symbols for momentum (>={min_return_pct}% in {lookback_days}d)"
        )

        for batch_idx in range(0, len(candidates), BARS_BATCH_SIZE):
            batch = candidates[batch_idx : batch_idx + BARS_BATCH_SIZE]
            try:
                request = StockBarsRequest(
                    symbol_or_symbols=batch,
                    timeframe=TimeFrame.Day,
                    start=start_date,
                )
                bars_response = self._data_client.get_stock_bars(request)

                for symbol in batch:
                    symbol_bars = bars_response.get(symbol, [])
                    if not symbol_bars or len(symbol_bars) < lookback_days:
                        continue

                    recent_bars = symbol_bars[-lookback_days:]
                    first_close = float(recent_bars[0].close)
                    last_close = float(recent_bars[-1].close)

                    if first_close <= 0:
                        continue

                    return_pct = ((last_close - first_close) / first_close) * 100

                    if abs(return_pct) >= min_return_pct:
                        avg_vol = sum(b.volume for b in recent_bars) / len(recent_bars)
                        momentum_candidates.append(
                            {
                                "symbol": symbol,
                                "return_pct": round(return_pct, 2),
                                "avg_volume": avg_vol,
                                "last_close": last_close,
                                "direction": "up" if return_pct > 0 else "down",
                            }
                        )

                time.sleep(BATCH_DELAY_SECONDS)

            except APIError as e:
                logger.warning(f"API error during momentum scan: {e}")
                time.sleep(2.0)
            except Exception as e:
                logger.error(f"Error during momentum scan: {e}")

        # Sort by absolute return (strongest momentum first)
        momentum_candidates.sort(key=lambda x: abs(x["return_pct"]), reverse=True)

        logger.info(f"Found {len(momentum_candidates)} momentum candidates >= {min_return_pct}%")
        for m in momentum_candidates[:10]:
            logger.info(
                f"  Momentum: {m['symbol']} {m['direction']} {m['return_pct']:+.1f}% "
                f"(vol {m['avg_volume']:,.0f}, ${m['last_close']:.2f})"
            )

        return momentum_candidates
