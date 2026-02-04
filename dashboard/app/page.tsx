'use client';

import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';
import { StrategyPerformanceChart } from '@/components/charts/strategy-performance';
import { RecentTrades } from '@/components/recent-trades';
import { StatusCard } from '@/components/status-card';
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Activity,
  BarChart3,
  Clock,
  LogOut,
} from 'lucide-react';

export default function Dashboard() {
  const router = useRouter();

  const { data: portfolio, isLoading: portfolioLoading } = useQuery({
    queryKey: ['portfolio'],
    queryFn: api.getPortfolioSummary,
  });

  const { data: strategies, isLoading: strategiesLoading } = useQuery({
    queryKey: ['strategies'],
    queryFn: api.getStrategies,
  });

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: api.getTradingStatus,
  });

  const isLoading = portfolioLoading || strategiesLoading;

  const handleLogout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/login');
    router.refresh();
  };

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
        <div className="flex items-center gap-4">
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
          <button
            onClick={handleLogout}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <LogOut className="h-4 w-4" />
            Logout
          </button>
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
          subtitle="of 10 max"
          icon={Activity}
          loading={isLoading}
        />
        <StatusCard
          title="Trades Today"
          value={portfolio?.trades_today?.toString() || '0'}
          subtitle="of 30 max"
          icon={Clock}
          loading={isLoading}
        />
      </div>

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

      {/* Recent Trades */}
      <div className="rounded-lg border bg-card p-6">
        <h2 className="text-lg font-semibold mb-4">Recent Trades</h2>
        <RecentTrades />
      </div>
    </div>
  );
}
