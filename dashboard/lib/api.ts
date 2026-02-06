/**
 * API client for the Bringetto Trading Agent
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || '';

// ============================================================================
// Types
// ============================================================================

export interface Trade {
  id: string;
  timestamp: string;
  symbol: string;
  strategy_id: string;
  strategy_name: string;
  side: 'buy' | 'sell';
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  pnl: number | null;
  pnl_percent: number | null;
  commission: number;
  status: 'open' | 'closed' | 'cancelled' | 'partial';
  entry_time: string;
  exit_time: string | null;
  holding_time_seconds: number | null;
  stop_loss: number;
  take_profit: number;
}

export interface StrategyPerformance {
  strategy_id: string;
  name: string;
  strategy_type: string;
  is_enabled: boolean;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_pnl: number;
  profit_factor: number;
  sharpe_ratio: number | null;
  max_drawdown: number | null;
}

export interface TradingStatus {
  is_running: boolean;
  can_trade: boolean;
  reason: string;
  circuit_breaker_active: boolean;
  current_session?: 'overnight' | 'pre_market' | 'regular' | 'after_hours' | null;
  session_trading_enabled?: boolean | null;
}

export interface PortfolioSummary {
  account_value: number;
  cash: number;
  buying_power: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  open_positions: number;
  trades_today: number;
}

export interface DailySummary {
  date: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number | null;
  total_pnl: number;
  total_pnl_pct: number | null;
  best_trade: number | null;
  worst_trade: number | null;
  sharpe_ratio: number | null;
  profit_factor: number | null;
  account_balance: number | null;
}

export interface HealthStatus {
  status: string;
  timestamp: string;
  environment: string;
  database: boolean;
  alpaca: boolean;
  active_strategies: number;
  open_positions: number;
}

export interface ActivePosition {
  symbol: string;
  side: 'buy' | 'sell';
  quantity: number;
  entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
}

export interface TradeDecision {
  id: string;
  trade_id: string | null;
  timestamp: string;
  decision_type: 'entry' | 'exit' | 'hold' | 'skip';
  strategy_name: string;
  symbol: string;
  price: number;
  reasoning_text: string;
  confidence_score: number | null;
  outcome: string | null;
  what_worked: string | null;
  what_failed: string | null;
}

// Analytics types
export interface TimeOfDayPerformance {
  hour: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number | null;
  total_pnl: number;
  avg_pnl: number | null;
}

export interface SymbolPerformance {
  symbol: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number | null;
  total_pnl: number;
  avg_pnl: number | null;
  largest_win: number | null;
  largest_loss: number | null;
}

export interface StrategyComparison {
  name: string;
  strategy_type: string;
  is_active: boolean;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number | null;
  total_pnl: number;
  profit_factor: number | null;
  sharpe_ratio: number | null;
  max_drawdown: number | null;
  avg_holding_time_seconds: number | null;
}

export interface RiskMetrics {
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  max_drawdown: number | null;
  max_drawdown_duration_days: number | null;
  calmar_ratio: number | null;
  win_rate: number | null;
  profit_factor: number | null;
  avg_win: number | null;
  avg_loss: number | null;
  expectancy: number | null;
  risk_reward_ratio: number | null;
}

export interface PnLCurvePoint {
  date: string;
  cumulative_pnl: number;
  daily_pnl: number;
  trade_count: number;
}

export interface TradeDistribution {
  pnl_ranges: { range: string; count: number }[];
  holding_time_distribution: { range: string; count: number }[];
  side_distribution: { buy: number; sell: number };
}

// Market status types
export interface MarketStatus {
  is_open: boolean;
  current_session: 'overnight' | 'pre_market' | 'regular' | 'after_hours' | 'unknown';
  session_display: string;
  next_open: string | null;
  next_close: string | null;
  timestamp: string;
  can_trade_regular: boolean;
  can_trade_extended: boolean;
  can_trade_overnight: boolean;
}

export interface AssetInfo {
  symbol: string;
  name: string | null;
  exchange: string | null;
  status: string | null;
  tradable: boolean;
  fractionable: boolean;
  marginable: boolean;
  shortable: boolean;
  easy_to_borrow: boolean;
  overnight_tradable: boolean;
  has_options: boolean;
}

export interface Quote {
  symbol: string;
  bid: number;
  ask: number;
  bid_size: number;
  ask_size: number;
  timestamp: string;
  error?: string;
}

// Instrumentation types
export interface DataReceptionStats {
  total_bars: number;
  total_quotes: number;
  total_trades: number;
  unique_symbols_bars: number;
  unique_symbols_quotes: number;
  unique_symbols_trades: number;
  first_data_time: string | null;
  last_data_time: string | null;
  data_freshness_seconds: number | null;
  bars_per_second: number;
  quotes_per_second: number;
  trades_per_second: number;
}

export interface StrategyEvaluation {
  id: string;
  timestamp: string;
  strategy_name: string;
  symbol: string;
  evaluation_type: 'entry' | 'exit';
  decision: 'accepted' | 'rejected' | 'skipped';
  context: Record<string, unknown>;
  rejection_reason: string | null;
  signal: Record<string, unknown> | null;
}

// Funnel data for the decision pipeline
export interface FunnelData {
  skipped_no_data?: number;  // Only in aggregate
  signal_generated: number;
  blocked_pdt: number;
  blocked_risk_validation: number;
  blocked_position_size: number;
  orders_submitted: number;
  orders_failed: number;
  orders_filled: number;
  trades_closed: number;
  trades_won: number;
  trades_lost: number;
}

export interface RiskRejectionBreakdown {
  market_hours: number;
  no_stop_loss: number;
  invalid_stop_loss: number;
  position_size: number;
  buying_power: number;
  daytrading_buying_power: number;  // DTMC prevention
  max_positions: number;
  max_exposure: number;
  min_price: number;
  [key: string]: number;  // Index signature for Record<string, number> compatibility
}

export interface StrategyEvaluationStats {
  total: number;
  accepted: number;
  rejected: number;
  funnel?: FunnelData;
  risk_rejection_breakdown?: Record<string, number>;
}

export interface EvaluationSummary {
  total_evaluations: number;
  accepted: number;
  rejected: number;
  skipped: number;
  acceptance_rate: number;
  by_strategy: Record<string, StrategyEvaluationStats>;
  by_symbol: Record<string, number>;
  time_window_minutes: number;
  funnel?: FunnelData;
  risk_rejection_breakdown?: RiskRejectionBreakdown;
}

export interface InstrumentationStatus {
  data_reception: DataReceptionStats;
  evaluations: EvaluationSummary;
  recent_accepted_signals: StrategyEvaluation[];
}

// Valid time range values for instrumentation queries
export type InstrumentationTimeRange = 'session' | '1d' | '7d' | '30d';

// ============================================================================
// API Client
// ============================================================================

class ApiClient {
  private baseUrl: string;
  private apiKey: string;

  constructor(baseUrl: string, apiKey: string) {
    this.baseUrl = baseUrl;
    this.apiKey = apiKey;
  }

  private async fetch<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...(this.apiKey && { 'X-API-Key': this.apiKey }),
      ...options.headers,
    };

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `API error: ${response.status}`);
    }

    return response.json();
  }

  // --------------------------------------------------------------------------
  // Trades
  // --------------------------------------------------------------------------

  async getTrades(limit: number = 100, offset: number = 0): Promise<Trade[]> {
    return this.fetch<Trade[]>(
      `/api/trades/history?limit=${limit}&offset=${offset}`
    );
  }

  async getTradeById(tradeId: string): Promise<Trade> {
    return this.fetch<Trade>(`/api/trades/${tradeId}`);
  }

  async getTradeDecisions(tradeId: string): Promise<TradeDecision[]> {
    return this.fetch<TradeDecision[]>(`/api/trades/${tradeId}/decisions`);
  }

  async getActivePositions(): Promise<ActivePosition[]> {
    return this.fetch<ActivePosition[]>('/api/trades/active');
  }

  // --------------------------------------------------------------------------
  // Strategies
  // --------------------------------------------------------------------------

  async getStrategies(): Promise<StrategyPerformance[]> {
    // Use performance endpoint which includes trade counts and P&L data,
    // not /api/strategies/ which only returns config
    const response = await this.fetch<any[]>('/api/performance/strategies');
    return response.map((s) => ({
      strategy_id: s.name,
      name: s.name,
      strategy_type: s.type,
      is_enabled: s.is_active,
      total_trades: s.trades_today || 0,
      winning_trades: 0,
      losing_trades: 0,
      win_rate: s.win_rate || 0,
      total_pnl: s.pnl_today || 0,
      profit_factor: s.profit_factor || 0,
      sharpe_ratio: null,
      max_drawdown: null,
    }));
  }

  async toggleStrategy(strategyName: string, enabled: boolean): Promise<void> {
    await this.fetch(`/api/strategies/${strategyName}/toggle`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    });
  }

  async updateStrategyParameters(
    strategyName: string,
    parameters: Record<string, number>
  ): Promise<void> {
    await this.fetch(`/api/strategies/${strategyName}/parameters`, {
      method: 'PATCH',
      body: JSON.stringify(parameters),
    });
  }

  // --------------------------------------------------------------------------
  // Performance
  // --------------------------------------------------------------------------

  async getPortfolioSummary(): Promise<PortfolioSummary> {
    const summary = await this.fetch<any>('/api/performance/summary');
    const equity = summary.account?.equity || 0;
    const dailyPnl = summary.today?.pnl || 0;
    return {
      account_value: equity,
      cash: summary.account?.cash || 0,
      buying_power: summary.account?.buying_power || 0,
      daily_pnl: dailyPnl,
      daily_pnl_pct: equity > 0 ? (dailyPnl / equity) * 100 : 0,
      open_positions: summary.today?.open_positions || 0,
      trades_today: summary.today?.trades || 0,
    };
  }

  async getDailyPerformance(days: number = 30): Promise<DailySummary[]> {
    return this.fetch<DailySummary[]>(
      `/api/performance/daily?days=${days}`
    );
  }

  async getStrategyPerformance(): Promise<StrategyPerformance[]> {
    const response = await this.fetch<any[]>('/api/performance/strategies');
    return response.map((s) => ({
      strategy_id: s.name,
      name: s.name,
      strategy_type: s.type,
      is_enabled: s.is_active,
      total_trades: s.trades_today || 0,
      winning_trades: 0,
      losing_trades: 0,
      win_rate: s.win_rate || 0,
      total_pnl: s.pnl_today || 0,
      profit_factor: s.profit_factor || 0,
      sharpe_ratio: null,
      max_drawdown: null,
    }));
  }

  async getEquityCurve(
    period: '1D' | '1W' | '1M' | '3M' | '6M' | '1Y' | 'ALL' = '1M'
  ): Promise<{ date: string; equity: number }[]> {
    return this.fetch(`/api/performance/equity-curve?period=${period}`);
  }

  // --------------------------------------------------------------------------
  // Controls
  // --------------------------------------------------------------------------

  async getTradingStatus(): Promise<TradingStatus> {
    return this.fetch<TradingStatus>('/api/controls/status');
  }

  async pauseTrading(): Promise<void> {
    await this.fetch('/api/controls/pause', { method: 'POST' });
  }

  async resumeTrading(): Promise<void> {
    await this.fetch('/api/controls/resume', { method: 'POST' });
  }

  async activateKillSwitch(): Promise<{ positions_closed: number; orders_cancelled: number }> {
    return this.fetch('/api/controls/kill-switch', { method: 'POST' });
  }

  async resetCircuitBreaker(): Promise<void> {
    await this.fetch('/api/controls/circuit-breaker/reset', { method: 'POST' });
  }

  // --------------------------------------------------------------------------
  // Health
  // --------------------------------------------------------------------------

  async getHealth(): Promise<HealthStatus> {
    return this.fetch<HealthStatus>('/health');
  }

  // --------------------------------------------------------------------------
  // Analytics
  // --------------------------------------------------------------------------

  async getTimeOfDayPerformance(days: number = 30): Promise<TimeOfDayPerformance[]> {
    return this.fetch<TimeOfDayPerformance[]>(
      `/api/analytics/time-of-day?days=${days}`
    );
  }

  async getSymbolPerformance(
    days: number = 30,
    limit: number = 20
  ): Promise<SymbolPerformance[]> {
    return this.fetch<SymbolPerformance[]>(
      `/api/analytics/symbol-performance?days=${days}&limit=${limit}`
    );
  }

  async getStrategyComparison(days: number = 30): Promise<StrategyComparison[]> {
    return this.fetch<StrategyComparison[]>(
      `/api/analytics/strategy-comparison?days=${days}`
    );
  }

  async getRiskMetrics(days: number = 30): Promise<RiskMetrics> {
    return this.fetch<RiskMetrics>(`/api/analytics/risk-metrics?days=${days}`);
  }

  async getPnLCurve(days: number = 30): Promise<PnLCurvePoint[]> {
    return this.fetch<PnLCurvePoint[]>(`/api/analytics/pnl-curve?days=${days}`);
  }

  async getTradeDistribution(days: number = 30): Promise<TradeDistribution> {
    return this.fetch<TradeDistribution>(
      `/api/analytics/trade-distribution?days=${days}`
    );
  }

  // --------------------------------------------------------------------------
  // Market
  // --------------------------------------------------------------------------

  async getMarketStatus(): Promise<MarketStatus> {
    return this.fetch<MarketStatus>('/api/market/status');
  }

  async getAssetInfo(symbol: string): Promise<AssetInfo> {
    return this.fetch<AssetInfo>(`/api/market/asset/${symbol}`);
  }

  async getQuote(symbol: string): Promise<Quote> {
    return this.fetch<Quote>(`/api/market/quote/${symbol}`);
  }

  // --------------------------------------------------------------------------
  // Instrumentation
  // --------------------------------------------------------------------------

  async getInstrumentationStatus(
    timeRange: InstrumentationTimeRange = 'session'
  ): Promise<InstrumentationStatus> {
    return this.fetch<InstrumentationStatus>(
      `/api/instrumentation/?time_range=${timeRange}`
    );
  }

  async getDataReceptionStats(
    timeRange: InstrumentationTimeRange = 'session'
  ): Promise<DataReceptionStats> {
    return this.fetch<DataReceptionStats>(
      `/api/instrumentation/data-reception?time_range=${timeRange}`
    );
  }

  async getEvaluations(
    minutes: number = 60,
    strategyName?: string,
    symbol?: string,
    decision?: string,
    limit: number = 100
  ): Promise<StrategyEvaluation[]> {
    const params = new URLSearchParams({
      minutes: minutes.toString(),
      limit: limit.toString(),
    });
    if (strategyName) params.append('strategy_name', strategyName);
    if (symbol) params.append('symbol', symbol);
    if (decision) params.append('decision', decision);
    return this.fetch<StrategyEvaluation[]>(`/api/instrumentation/evaluations?${params}`);
  }

  async getEvaluationSummary(
    minutes: number = 60,
    timeRange: InstrumentationTimeRange = 'session'
  ): Promise<EvaluationSummary> {
    return this.fetch<EvaluationSummary>(
      `/api/instrumentation/evaluations/summary?minutes=${minutes}&time_range=${timeRange}`
    );
  }
}

// Export singleton instance
export const api = new ApiClient(API_BASE_URL, API_KEY);

// Export the class for testing or custom instances
export { ApiClient };
