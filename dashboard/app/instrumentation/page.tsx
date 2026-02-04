'use client';

import { useQuery } from '@tanstack/react-query';
import { api, DataReceptionStats, EvaluationSummary, StrategyEvaluation } from '@/lib/api';
import {
  Activity,
  BarChart3,
  CheckCircle,
  XCircle,
  Clock,
  Zap,
  Database,
  RefreshCw,
} from 'lucide-react';
import { useTimezoneStore, formatTimeInTimezone, TIMEZONE_OPTIONS } from '@/lib/timezone-store';

export default function InstrumentationPage() {
  const { data: status, isLoading, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['instrumentation-status'],
    queryFn: () => api.getInstrumentationStatus(),
    refetchInterval: 5000, // Refresh every 5 seconds
  });

  const { data: evaluations } = useQuery({
    queryKey: ['evaluations'],
    queryFn: () => api.getEvaluations(60, undefined, undefined, undefined, 50),
    refetchInterval: 5000,
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Instrumentation</h1>
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-48 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Instrumentation</h1>
          <p className="text-muted-foreground">
            Real-time observability for market data and trade decisions
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm hover:bg-muted transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Data Reception Section */}
      <section>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Database className="h-5 w-5" />
          Data Reception Status
        </h2>
        {status?.data_reception ? (
          <DataReceptionCard stats={status.data_reception} />
        ) : (
          <div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
            No data reception stats available
          </div>
        )}
      </section>

      {/* Evaluation Summary Section */}
      <section>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <BarChart3 className="h-5 w-5" />
          Strategy Evaluation Summary
        </h2>
        {status?.evaluations ? (
          <EvaluationSummaryCard summary={status.evaluations} />
        ) : (
          <div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
            No evaluation data available
          </div>
        )}
      </section>

      {/* Recent Evaluations Section */}
      <section>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Activity className="h-5 w-5" />
          Recent Evaluations
        </h2>
        {evaluations && evaluations.length > 0 ? (
          <EvaluationsList evaluations={evaluations} />
        ) : (
          <div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
            No recent evaluations. Evaluations will appear here once the trading loop starts evaluating strategies.
          </div>
        )}
      </section>

      {/* Last Updated */}
      <LastUpdatedFooter timestamp={dataUpdatedAt} />
    </div>
  );
}

function LastUpdatedFooter({ timestamp }: { timestamp: number }) {
  const { timezone } = useTimezoneStore();
  const tzOption = TIMEZONE_OPTIONS.find((tz) => tz.value === timezone);

  return (
    <p className="text-xs text-muted-foreground text-right">
      Last updated: {formatTimeInTimezone(new Date(timestamp))} {tzOption?.abbrev}
    </p>
  );
}

function DataReceptionCard({ stats }: { stats: DataReceptionStats }) {
  const isReceivingData = stats.total_bars > 0 || stats.total_quotes > 0 || stats.total_trades > 0;
  const isFresh = stats.data_freshness_seconds !== null && stats.data_freshness_seconds < 60;

  return (
    <div className="rounded-lg border bg-card p-6">
      {/* Status Banner */}
      <div
        className={`mb-4 rounded-lg p-3 flex items-center gap-2 ${
          isReceivingData && isFresh
            ? 'bg-green-100 text-green-800'
            : isReceivingData
            ? 'bg-yellow-100 text-yellow-800'
            : 'bg-red-100 text-red-800'
        }`}
      >
        {isReceivingData && isFresh ? (
          <>
            <Zap className="h-5 w-5" />
            <span className="font-medium">Data Flowing</span>
            {stats.data_freshness_seconds !== null && (
              <span className="ml-auto text-sm">
                Last data: {stats.data_freshness_seconds.toFixed(1)}s ago
              </span>
            )}
          </>
        ) : isReceivingData ? (
          <>
            <Clock className="h-5 w-5" />
            <span className="font-medium">Data Stale</span>
            {stats.data_freshness_seconds !== null && (
              <span className="ml-auto text-sm">
                Last data: {stats.data_freshness_seconds.toFixed(0)}s ago
              </span>
            )}
          </>
        ) : (
          <>
            <XCircle className="h-5 w-5" />
            <span className="font-medium">No Data Received</span>
          </>
        )}
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatBox
          label="Bars Received"
          value={stats.total_bars.toLocaleString()}
          subValue={`${stats.bars_per_second.toFixed(2)}/sec`}
          subLabel={`${stats.unique_symbols_bars} symbols`}
        />
        <StatBox
          label="Quotes Received"
          value={stats.total_quotes.toLocaleString()}
          subValue={`${stats.quotes_per_second.toFixed(2)}/sec`}
          subLabel={`${stats.unique_symbols_quotes} symbols`}
        />
        <StatBox
          label="Trades Received"
          value={stats.total_trades.toLocaleString()}
          subValue={`${stats.trades_per_second.toFixed(2)}/sec`}
          subLabel={`${stats.unique_symbols_trades} symbols`}
        />
        <StatBox
          label="Data Window"
          value={
            stats.first_data_time
              ? formatTimeInTimezone(stats.first_data_time)
              : 'N/A'
          }
          subValue={
            stats.last_data_time
              ? formatTimeInTimezone(stats.last_data_time)
              : 'N/A'
          }
          subLabel="First / Last"
        />
      </div>
    </div>
  );
}

function EvaluationSummaryCard({ summary }: { summary: EvaluationSummary }) {
  const strategies = Object.entries(summary.by_strategy || {});

  return (
    <div className="rounded-lg border bg-card p-6">
      {/* Overall Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatBox
          label="Total Evaluations"
          value={summary.total_evaluations.toLocaleString()}
          subValue="Session total"
        />
        <StatBox
          label="Accepted"
          value={summary.accepted.toLocaleString()}
          highlight="green"
        />
        <StatBox
          label="Rejected"
          value={summary.rejected.toLocaleString()}
          highlight="red"
        />
        <StatBox
          label="Acceptance Rate"
          value={`${(summary.acceptance_rate * 100).toFixed(1)}%`}
          highlight={summary.acceptance_rate > 0.1 ? 'green' : undefined}
        />
      </div>

      {/* By Strategy Breakdown */}
      {strategies.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-muted-foreground mb-3">
            By Strategy
          </h3>
          <div className="space-y-2">
            {strategies.map(([name, data]) => (
              <div
                key={name}
                className="flex items-center justify-between rounded-lg bg-muted/50 px-4 py-2"
              >
                <span className="font-medium">{name}</span>
                <div className="flex items-center gap-4 text-sm">
                  <span className="text-muted-foreground">
                    {data.total} total
                  </span>
                  <span className="text-green-600 flex items-center gap-1">
                    <CheckCircle className="h-3 w-3" />
                    {data.accepted}
                  </span>
                  <span className="text-red-600 flex items-center gap-1">
                    <XCircle className="h-3 w-3" />
                    {data.rejected}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {summary.total_evaluations === 0 && (
        <p className="text-center text-muted-foreground py-4">
          No evaluations yet. Strategy evaluations will appear here once trading is active.
        </p>
      )}
    </div>
  );
}

function EvaluationsList({ evaluations }: { evaluations: StrategyEvaluation[] }) {
  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <div className="max-h-96 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 sticky top-0">
            <tr>
              <th className="text-left px-4 py-2 font-medium">Time</th>
              <th className="text-left px-4 py-2 font-medium">Strategy</th>
              <th className="text-left px-4 py-2 font-medium">Symbol</th>
              <th className="text-left px-4 py-2 font-medium">Type</th>
              <th className="text-left px-4 py-2 font-medium">Decision</th>
              <th className="text-left px-4 py-2 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {evaluations.map((evaluation) => (
              <tr key={evaluation.id} className="hover:bg-muted/30">
                <td className="px-4 py-2 text-muted-foreground">
                  {formatTimeInTimezone(evaluation.timestamp)}
                </td>
                <td className="px-4 py-2 font-medium">
                  {evaluation.strategy_name}
                </td>
                <td className="px-4 py-2">{evaluation.symbol}</td>
                <td className="px-4 py-2 capitalize">{evaluation.evaluation_type}</td>
                <td className="px-4 py-2">
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
                      evaluation.decision === 'accepted'
                        ? 'bg-green-100 text-green-800'
                        : evaluation.decision === 'rejected'
                        ? 'bg-red-100 text-red-800'
                        : 'bg-gray-100 text-gray-800'
                    }`}
                  >
                    {evaluation.decision === 'accepted' ? (
                      <CheckCircle className="h-3 w-3" />
                    ) : (
                      <XCircle className="h-3 w-3" />
                    )}
                    {evaluation.decision}
                  </span>
                </td>
                <td className="px-4 py-2 text-muted-foreground truncate max-w-xs">
                  {evaluation.rejection_reason || (evaluation.signal ? 'Signal generated' : '-')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatBox({
  label,
  value,
  subValue,
  subLabel,
  highlight,
}: {
  label: string;
  value: string;
  subValue?: string;
  subLabel?: string;
  highlight?: 'green' | 'red';
}) {
  return (
    <div className="text-center">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p
        className={`text-2xl font-bold ${
          highlight === 'green'
            ? 'text-green-600'
            : highlight === 'red'
            ? 'text-red-600'
            : ''
        }`}
      >
        {value}
      </p>
      {subValue && (
        <p className="text-xs text-muted-foreground">{subValue}</p>
      )}
      {subLabel && (
        <p className="text-xs text-muted-foreground">{subLabel}</p>
      )}
    </div>
  );
}
