'use client';

import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';
import { StrategyPerformanceChart } from '@/components/charts/strategy-performance';
import { RecentTrades } from '@/components/recent-trades';
import { StatusCard } from '@/components/status-card';
import {
  DataReceptionCard,
  FunnelCard,
  EvaluationSummaryCard,
  EvaluationsList,
} from '@/components/instrumentation-widgets';
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Activity,
  BarChart3,
  Clock,
  Database,
} from 'lucide-react';
import { useTimezoneStore, TIMEZONE_OPTIONS } from '@/lib/timezone-store';

export default function Dashboard() {
  const { data: portfolio, isLoading: portfolioLoading } = useQuery({
    queryKey: ['portfolio'],
    queryFn: () => api.getPortfolioSummary(),
  });

  const { data: strategies, isLoading: strategiesLoading } = useQuery({
    queryKey: ['strategies'],
    queryFn: () => api.getStrategies(),
  });

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: () => api.getTradingStatus(),
  });

  const { data: instrumentationStatus, dataUpdatedAt } = useQuery({
    queryKey: ['instrumentation-status'],
    queryFn: () => api.getInstrumentationStatus('session'),
    refetchInterval: 5000,
  });

  const { data: evaluations } = useQuery({
    queryKey: ['evaluations'],
    queryFn: () => api.getEvaluations(60, undefined, undefined, undefined, 50),
    refetchInterval: 5000,
  });

  const isLoading = portfolioLoading || strategiesLoading;
  const limitsDisabled = portfolio?.trading_limits_disabled ?? false;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground">
            Real-time trading performance overview
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div
            className={`h-3 w-3 rounded-full ${
              status?.is_running ? 'bg-green-500' : 'bg-red-500'
            }`}
          />
          <span className="text-sm text-muted-foreground">
            {status?.is_running ? 'Trading Active' : 'Trading Paused'}
          </span>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatusCard
          title="Account Value"
          value={portfolio ? formatCurrency(portfolio.account_value) : '-'}
          icon={DollarSign}
          loading={isLoading}
        />
        <StatusCard
          title="Daily P&L"
          value={portfolio ? formatCurrency(portfolio.daily_pnl) : '-'}
          subtitle={portfolio ? formatPercent(portfolio.daily_pnl_pct) : undefined}
          icon={(portfolio?.daily_pnl ?? 0) >= 0 ? TrendingUp : TrendingDown}
          trend={(portfolio?.daily_pnl ?? 0) >= 0 ? 'up' : 'down'}
          loading={isLoading}
        />
        <StatusCard
          title="Open Positions"
          value={portfolio?.open_positions?.toString() || '0'}
          subtitle={limitsDisabled ? 'no limit' : `of ${portfolio?.max_positions ?? 10} max`}
          icon={Activity}
          loading={isLoading}
        />
        <StatusCard
          title="Trades Today"
          value={portfolio?.trades_today?.toString() || '0'}
          subtitle={limitsDisabled ? 'no limit' : `of ${portfolio?.max_trades ?? 30} max`}
          icon={Clock}
          loading={isLoading}
        />
      </div>

      {/* Data Reception Status */}
      <section>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Database className="h-5 w-5" />
          Data Reception
        </h2>
        {instrumentationStatus?.data_reception ? (
          <DataReceptionCard stats={instrumentationStatus.data_reception} />
        ) : (
          <div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
            No data reception stats available
          </div>
        )}
      </section>

      {/* Charts Row */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Strategy Performance */}
        <div className="rounded-lg border bg-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="h-5 w-5 text-muted-foreground" />
            <h2 className="text-lg font-semibold">Strategy Performance</h2>
          </div>
          {strategies && strategies.length > 0 ? (
            <StrategyPerformanceChart strategies={strategies} />
          ) : (
            <div className="h-[300px] flex items-center justify-center text-muted-foreground">
              No strategy data yet
            </div>
          )}
        </div>

        {/* Strategy Stats Table */}
        <div className="rounded-lg border bg-card p-6">
          <h2 className="text-lg font-semibold mb-4">Strategy Breakdown</h2>
          <div className="space-y-3">
            {strategies?.map((strategy) => (
              <div
                key={strategy.strategy_id}
                className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
              >
                <div>
                  <p className="font-medium">{strategy.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {strategy.total_trades} trades | {formatPercent(strategy.win_rate)} win rate
                  </p>
                </div>
                <div className="text-right">
                  <p
                    className={`font-semibold ${
                      strategy.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}
                  >
                    {formatCurrency(strategy.total_pnl)}
                  </p>
                  <div
                    className={`text-xs px-2 py-0.5 rounded ${
                      strategy.is_enabled
                        ? 'bg-green-100 text-green-700'
                        : 'bg-red-100 text-red-700'
                    }`}
                  >
                    {strategy.is_enabled ? 'Active' : 'Disabled'}
                  </div>
                </div>
              </div>
            ))}
            {!strategies?.length && (
              <p className="text-center text-muted-foreground py-8">
                No strategies configured
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Decision Pipeline Funnel */}
      <section>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <TrendingDown className="h-5 w-5" />
          Decision Pipeline
        </h2>
        {instrumentationStatus?.evaluations?.funnel ? (
          <FunnelCard
            funnel={instrumentationStatus.evaluations.funnel}
            riskBreakdown={instrumentationStatus.evaluations.risk_rejection_breakdown}
            totalEvaluations={instrumentationStatus.evaluations.total_evaluations}
          />
        ) : (
          <div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
            No funnel data available
          </div>
        )}
      </section>

      {/* Recent Trades */}
      <div className="rounded-lg border bg-card p-6">
        <h2 className="text-lg font-semibold mb-4">Recent Trades</h2>
        <RecentTrades />
      </div>

      {/* Strategy Evaluation Summary */}
      <section>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <BarChart3 className="h-5 w-5" />
          Evaluation Summary
        </h2>
        {instrumentationStatus?.evaluations ? (
          <EvaluationSummaryCard summary={instrumentationStatus.evaluations} />
        ) : (
          <div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
            No evaluation data available
          </div>
        )}
      </section>

      {/* Recent Evaluations */}
      <section>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Activity className="h-5 w-5" />
          Recent Evaluations
        </h2>
        {evaluations && evaluations.length > 0 ? (
          <EvaluationsList evaluations={evaluations} />
        ) : (
          <div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
            No recent evaluations. Evaluations will appear here once the trading loop starts.
          </div>
        )}
      </section>

      {/* Last Updated */}
      {dataUpdatedAt > 0 && <LastUpdatedFooter timestamp={dataUpdatedAt} />}
    </div>
  );
}

function LastUpdatedFooter({ timestamp }: { timestamp: number }) {
  const { timezone } = useTimezoneStore();
  const tzOption = TIMEZONE_OPTIONS.find((tz) => tz.value === timezone);

  const formattedTime = new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  }).format(new Date(timestamp));

  return (
    <p className="text-xs text-muted-foreground text-right">
      Last updated: {formattedTime} {tzOption?.abbrev}
    </p>
  );
}
