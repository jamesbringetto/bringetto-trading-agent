'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';
import { StrategyPerformanceChart } from '@/components/charts/strategy-performance';
import { MarketStatusWidget } from '@/components/market-status';
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
  ToggleLeft,
  ToggleRight,
} from 'lucide-react';

export default function Dashboard() {
  const router = useRouter();
  const queryClient = useQueryClient();

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

  const [limitsDisabledLocal, setLimitsDisabledLocal] = useState<boolean | null>(null);

  const toggleLimitsMutation = useMutation({
    mutationFn: (disabled: boolean) => api.toggleTradingLimits(disabled),
    onMutate: async (disabled: boolean) => {
      // Cancel outgoing refetches so they don't overwrite our optimistic update
      await queryClient.cancelQueries({ queryKey: ['portfolio'] });
      // Optimistically update local state immediately
      setLimitsDisabledLocal(disabled);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
      queryClient.invalidateQueries({ queryKey: ['status'] });
    },
    onError: () => {
      // Revert optimistic update on failure
      setLimitsDisabledLocal(null);
    },
    onSettled: () => {
      // Sync local override with server state after refetch completes
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
    },
  });

  const isLoading = portfolioLoading || strategiesLoading;
  // Use local optimistic state if set, otherwise fall back to server state
  const limitsDisabled = limitsDisabledLocal ?? portfolio?.trading_limits_disabled ?? false;

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

      {/* Trading Limits Toggle */}
      <div
        className={`flex items-center justify-between rounded-lg border p-4 ${
          limitsDisabled
            ? 'border-amber-500/50 bg-amber-500/10'
            : 'bg-card'
        }`}
      >
        <div className="flex items-center gap-3">
          <div>
            <p className="font-medium text-sm">
              Trading Limits (Paper Mode)
            </p>
            <p className="text-xs text-muted-foreground">
              {limitsDisabled
                ? 'Position and trade count limits are disabled'
                : 'Max 10 open positions, 30 trades per day'}
            </p>
          </div>
        </div>
        <button
          onClick={() => toggleLimitsMutation.mutate(!limitsDisabled)}
          className="flex items-center gap-2 text-sm cursor-pointer rounded-md px-3 py-2 transition-colors hover:bg-muted/80"
        >
          {limitsDisabled ? (
            <>
              <span className="text-amber-600 font-medium">Limits Off</span>
              <ToggleRight className="h-7 w-7 text-amber-500" />
            </>
          ) : (
            <>
              <span className="text-muted-foreground">Limits On</span>
              <ToggleLeft className="h-7 w-7 text-muted-foreground" />
            </>
          )}
        </button>
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

      {/* Market Status */}
      <div className="grid gap-6 lg:grid-cols-3">
        <MarketStatusWidget />
        <div className="lg:col-span-2 rounded-lg border bg-card p-6">
          <h2 className="text-lg font-semibold mb-4">24/5 Trading Schedule</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div className="p-3 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
              <p className="text-indigo-500 font-medium">Overnight</p>
              <p className="text-muted-foreground">8:00 PM - 4:00 AM ET</p>
            </div>
            <div className="p-3 rounded-lg bg-orange-500/10 border border-orange-500/20">
              <p className="text-orange-500 font-medium">Pre-Market</p>
              <p className="text-muted-foreground">4:00 AM - 9:30 AM ET</p>
            </div>
            <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/20">
              <p className="text-green-500 font-medium">Regular</p>
              <p className="text-muted-foreground">9:30 AM - 4:00 PM ET</p>
            </div>
            <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
              <p className="text-amber-500 font-medium">After Hours</p>
              <p className="text-muted-foreground">4:00 PM - 8:00 PM ET</p>
            </div>
          </div>
          <p className="mt-4 text-xs text-muted-foreground">
            Trading available Sunday 8 PM ET through Friday 8 PM ET. Overnight sessions support LIMIT orders only.
          </p>
        </div>
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
