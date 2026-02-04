'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, StrategyPerformance } from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';
import { ToggleLeft, ToggleRight, TrendingUp, TrendingDown } from 'lucide-react';

export default function StrategiesPage() {
  const queryClient = useQueryClient();

  const { data: strategies, isLoading } = useQuery({
    queryKey: ['strategies'],
    queryFn: () => api.getStrategies(),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api.toggleStrategy(id, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Strategies</h1>
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-32 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Strategies</h1>
        <p className="text-muted-foreground">
          Manage and monitor your 5 trading strategies
        </p>
      </div>

      <div className="grid gap-4">
        {strategies?.map((strategy) => (
          <StrategyCard
            key={strategy.strategy_id}
            strategy={strategy}
            onToggle={(enabled) =>
              toggleMutation.mutate({ id: strategy.strategy_id, enabled })
            }
          />
        ))}
      </div>
    </div>
  );
}

function StrategyCard({
  strategy,
  onToggle,
}: {
  strategy: StrategyPerformance;
  onToggle: (enabled: boolean) => void;
}) {
  const isProfitable = strategy.total_pnl >= 0;

  return (
    <div className="rounded-lg border bg-card p-6">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div
            className={`p-2 rounded-lg ${
              isProfitable ? 'bg-green-100' : 'bg-red-100'
            }`}
          >
            {isProfitable ? (
              <TrendingUp className="h-5 w-5 text-green-600" />
            ) : (
              <TrendingDown className="h-5 w-5 text-red-600" />
            )}
          </div>
          <div>
            <h3 className="font-semibold">{strategy.name}</h3>
            <p className="text-sm text-muted-foreground">
              {strategy.strategy_type.replace('_', ' ').toUpperCase()}
            </p>
          </div>
        </div>

        <button
          onClick={() => onToggle(!strategy.is_enabled)}
          className="flex items-center gap-2 text-sm"
        >
          {strategy.is_enabled ? (
            <>
              <ToggleRight className="h-6 w-6 text-green-500" />
              <span className="text-green-600">Enabled</span>
            </>
          ) : (
            <>
              <ToggleLeft className="h-6 w-6 text-muted-foreground" />
              <span className="text-muted-foreground">Disabled</span>
            </>
          )}
        </button>
      </div>

      <div className="mt-4 grid grid-cols-2 md:grid-cols-5 gap-4">
        <Stat label="Total P&L" value={formatCurrency(strategy.total_pnl)} highlight={isProfitable} />
        <Stat label="Win Rate" value={formatPercent(strategy.win_rate)} />
        <Stat label="Total Trades" value={strategy.total_trades.toString()} />
        <Stat label="Winning" value={strategy.winning_trades.toString()} />
        <Stat label="Profit Factor" value={strategy.profit_factor.toFixed(2)} />
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p
        className={`text-lg font-semibold ${
          highlight !== undefined
            ? highlight
              ? 'text-green-600'
              : 'text-red-600'
            : ''
        }`}
      >
        {value}
      </p>
    </div>
  );
}
