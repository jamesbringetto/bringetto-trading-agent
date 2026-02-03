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
    const response = await this.fetch<any[]>('/api/strategies/');
    // Transform API response to match expected interface
    return response.map((s) => ({
      strategy_id: s.name, // Use name as ID for now
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
    return {
      account_value: summary.account?.equity || 0,
      cash: summary.account?.cash || 0,
      buying_power: summary.account?.buying_power || 0,
      daily_pnl: summary.today?.pnl || 0,
      daily_pnl_pct: 0, // Calculate from pnl/account_value if needed
      open_positions: 0, // Get from active positions
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
}

// Export singleton instance
export const api = new ApiClient(API_BASE_URL, API_KEY);

// Export the class for testing or custom instances
export { ApiClient };
