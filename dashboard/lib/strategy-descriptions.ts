/**
 * Strategy descriptions for tooltip display across the dashboard.
 *
 * Maps strategy names (display names) and strategy types (snake_case)
 * to brief summary descriptions.
 */

const STRATEGY_DESCRIPTIONS: Record<string, string> = {
  // By display name
  'Opening Range Breakout':
    'Trades breakouts from the first 15–30 min price range on SPY, QQQ, and IWM.',
  'VWAP Mean Reversion':
    'Fades extreme deviations from VWAP on large-caps like AAPL, MSFT, GOOGL, NVDA, and TSLA.',
  'Momentum Scalp':
    'Rides strong intraday momentum on high-volume stocks (>5M daily volume) with quick entries and exits.',
  'Gap and Go':
    'Trades stocks that gap >3% in pre-market, capturing continuation moves after the open.',
  'EOD Reversal':
    'Catches mean-reversion moves in the final hour of trading on SPY and QQQ.',

  // By strategy type (snake_case keys from the API)
  opening_range_breakout:
    'Trades breakouts from the first 15–30 min price range on SPY, QQQ, and IWM.',
  vwap_mean_reversion:
    'Fades extreme deviations from VWAP on large-caps like AAPL, MSFT, GOOGL, NVDA, and TSLA.',
  momentum_scalp:
    'Rides strong intraday momentum on high-volume stocks (>5M daily volume) with quick entries and exits.',
  gap_and_go:
    'Trades stocks that gap >3% in pre-market, capturing continuation moves after the open.',
  eod_reversal:
    'Catches mean-reversion moves in the final hour of trading on SPY and QQQ.',
};

/**
 * Look up a strategy description by name or type.
 * Returns undefined if no match is found.
 */
export function getStrategyDescription(nameOrType: string): string | undefined {
  return STRATEGY_DESCRIPTIONS[nameOrType];
}
