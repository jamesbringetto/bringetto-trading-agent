'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import {
  AlertTriangle,
  Play,
  Pause,
  RefreshCw,
  LogOut,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react';

export default function SettingsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: () => api.getTradingStatus(),
    refetchInterval: 5000,
  });

  const { data: portfolio } = useQuery({
    queryKey: ['portfolio'],
    queryFn: () => api.getPortfolioSummary(),
  });

  const [limitsDisabledLocal, setLimitsDisabledLocal] = useState<boolean | null>(null);

  const toggleLimitsMutation = useMutation({
    mutationFn: (disabled: boolean) => api.toggleTradingLimits(disabled),
    onMutate: async (disabled: boolean) => {
      await queryClient.cancelQueries({ queryKey: ['portfolio'] });
      setLimitsDisabledLocal(disabled);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
      queryClient.invalidateQueries({ queryKey: ['status'] });
    },
    onError: () => {
      setLimitsDisabledLocal(null);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
    },
  });

  const killMutation = useMutation({
    mutationFn: () => api.activateKillSwitch(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['status'] });
    },
  });

  const pauseMutation = useMutation({
    mutationFn: () => api.pauseTrading(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['status'] });
    },
  });

  const resumeMutation = useMutation({
    mutationFn: () => api.resumeTrading(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['status'] });
    },
  });

  const limitsDisabled = limitsDisabledLocal ?? portfolio?.trading_limits_disabled ?? false;

  const handleLogout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/');
    router.refresh();
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold">Settings</h1>
          <p className="text-sm text-muted-foreground">
            Control your trading agent and manage system settings
          </p>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors self-start sm:self-auto"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </button>
      </div>

      {/* Trading Limits Toggle */}
      <div
        className={`flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-lg border p-4 ${
          limitsDisabled
            ? 'border-amber-500/50 bg-amber-500/10'
            : 'bg-card'
        }`}
      >
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
        <button
          onClick={() => toggleLimitsMutation.mutate(!limitsDisabled)}
          className="flex items-center gap-2 text-sm cursor-pointer rounded-md px-3 py-2 transition-colors hover:bg-muted/80 self-start sm:self-auto shrink-0"
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

      {/* Trading Status */}
      <div className="rounded-lg border bg-card p-4 sm:p-6">
        <h2 className="text-lg font-semibold mb-4">Trading Status</h2>
        <div className="space-y-4">
          <div className="flex items-center justify-between p-4 rounded-lg bg-muted/50">
            <div className="flex items-center gap-3">
              <div
                className={`h-3 w-3 rounded-full ${
                  status?.is_running ? 'bg-green-500' : 'bg-red-500'
                }`}
              />
              <div>
                <p className="font-medium">
                  {status?.is_running ? 'Trading Active' : 'Trading Paused'}
                </p>
                <p className="text-sm text-muted-foreground">{status?.reason}</p>
              </div>
            </div>
          </div>

          {status?.circuit_breaker_active && (
            <div className="flex items-center gap-3 p-4 rounded-lg bg-red-50 border border-red-200">
              <AlertTriangle className="h-5 w-5 text-red-500" />
              <div>
                <p className="font-medium text-red-700">Circuit Breaker Active</p>
                <p className="text-sm text-red-600">
                  Trading has been automatically paused due to loss limits
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Trading Controls */}
      <div className="rounded-lg border bg-card p-4 sm:p-6">
        <h2 className="text-lg font-semibold mb-4">Trading Controls</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {status?.is_running ? (
            <button
              onClick={() => pauseMutation.mutate()}
              disabled={pauseMutation.isPending}
              className="flex items-center justify-center gap-2 rounded-lg bg-yellow-500 px-4 py-3 font-medium text-white hover:bg-yellow-600 transition-colors disabled:opacity-50"
            >
              <Pause className="h-5 w-5" />
              Pause Trading
            </button>
          ) : (
            <button
              onClick={() => resumeMutation.mutate()}
              disabled={resumeMutation.isPending || status?.circuit_breaker_active}
              className="flex items-center justify-center gap-2 rounded-lg bg-green-500 px-4 py-3 font-medium text-white hover:bg-green-600 transition-colors disabled:opacity-50"
            >
              <Play className="h-5 w-5" />
              Resume Trading
            </button>
          )}

          <button
            onClick={() => queryClient.invalidateQueries()}
            className="flex items-center justify-center gap-2 rounded-lg bg-secondary px-4 py-3 font-medium hover:bg-secondary/80 transition-colors"
          >
            <RefreshCw className="h-5 w-5" />
            Refresh Data
          </button>

          <button
            onClick={() => {
              if (confirm('Are you sure? This will close ALL positions and stop trading.')) {
                killMutation.mutate();
              }
            }}
            disabled={killMutation.isPending}
            className="flex items-center justify-center gap-2 rounded-lg bg-red-500 px-4 py-3 font-medium text-white hover:bg-red-600 transition-colors disabled:opacity-50"
          >
            <AlertTriangle className="h-5 w-5" />
            Kill Switch
          </button>
        </div>
      </div>

      {/* Risk Limits */}
      <div className="rounded-lg border bg-card p-4 sm:p-6">
        <h2 className="text-lg font-semibold mb-4">Risk Limits (Read-Only)</h2>
        <p className="text-sm text-muted-foreground mb-4">
          These limits are configured in environment variables and cannot be changed from the dashboard.
        </p>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <LimitCard label="Max Daily Loss" value="2%" />
          <LimitCard label="Max Weekly Loss" value="5%" />
          <LimitCard label="Max Monthly Drawdown" value="10%" />
          <LimitCard label="Max Position Size" value="15%" />
          <LimitCard label="Max Risk Per Trade" value="1%" />
          <LimitCard label="Max Concurrent Positions" value="10" />
        </div>
      </div>
    </div>
  );
}

function LimitCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-4 rounded-lg bg-muted/50">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
    </div>
  );
}
