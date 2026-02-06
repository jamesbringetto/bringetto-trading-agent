'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, DataReceptionStats, EvaluationSummary, StrategyEvaluation, FunnelData, StrategyEvaluationStats } from '@/lib/api';
import {
  Activity,
  BarChart3,
  CheckCircle,
  XCircle,
  Clock,
  Zap,
  Database,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  ArrowRight,
} from 'lucide-react';
import { useTimezoneStore, TIMEZONE_OPTIONS } from '@/lib/timezone-store';
import { StrategyTooltip } from '@/components/strategy-tooltip';

export default function InstrumentationPage() {
  const { data: status, isLoading, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['instrumentation-status'],
    queryFn: () => api.getInstrumentationStatus('session'),
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
        <div className="flex items-center gap-3">
          <button
            onClick={() => refetch()}
            className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm hover:bg-muted transition-colors"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
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

      {/* Decision Funnel Section */}
      <section>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <TrendingDown className="h-5 w-5" />
          Decision Pipeline Funnel
        </h2>
        {status?.evaluations?.funnel ? (
          <FunnelCard
            funnel={status.evaluations.funnel}
            riskBreakdown={status.evaluations.risk_rejection_breakdown}
            totalEvaluations={status.evaluations.total_evaluations}
          />
        ) : (
          <div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
            No funnel data available
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

function DataReceptionCard({ stats }: { stats: DataReceptionStats }) {
  const { timezone } = useTimezoneStore();
  const isReceivingData = stats.total_bars > 0 || stats.total_quotes > 0 || stats.total_trades > 0;
  const isFresh = stats.data_freshness_seconds !== null && stats.data_freshness_seconds < 60;

  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    }).format(date);
  };

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
              ? formatTime(stats.first_data_time)
              : 'N/A'
          }
          subValue={
            stats.last_data_time
              ? formatTime(stats.last_data_time)
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
  const [expandedStrategy, setExpandedStrategy] = useState<string | null>(null);

  return (
    <div className="rounded-lg border bg-card p-6">
      {/* Overall Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatBox
          label="Total Evaluations"
          value={summary.total_evaluations.toLocaleString()}
          subValue="This Session"
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
            By Strategy (click to expand funnel)
          </h3>
          <div className="space-y-2">
            {strategies.map(([name, data]) => {
              const isExpanded = expandedStrategy === name;
              const funnel = data.funnel;
              const riskBreakdown = data.risk_rejection_breakdown;

              return (
                <div key={name}>
                  <button
                    onClick={() => setExpandedStrategy(isExpanded ? null : name)}
                    className="w-full flex items-center justify-between rounded-lg bg-muted/50 px-4 py-2 hover:bg-muted/70 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      )}
                      <StrategyTooltip name={name} className="font-medium">{name}</StrategyTooltip>
                    </div>
                    <div className="flex items-center gap-4 text-sm">
                      <span className="text-muted-foreground">
                        {data.total.toLocaleString()} total
                      </span>
                      <span className="text-green-600 flex items-center gap-1">
                        <CheckCircle className="h-3 w-3" />
                        {data.accepted.toLocaleString()}
                      </span>
                      <span className="text-red-600 flex items-center gap-1">
                        <XCircle className="h-3 w-3" />
                        {data.rejected.toLocaleString()}
                      </span>
                    </div>
                  </button>

                  {/* Expanded Funnel View */}
                  {isExpanded && funnel && (
                    <div className="mt-2 ml-6 p-4 rounded-lg bg-muted/30 border border-muted">
                      <div className="text-xs text-muted-foreground mb-3">Pipeline Progress</div>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                        <div className="text-center p-2 rounded bg-green-100">
                          <p className="text-green-800 font-medium">{funnel.signal_generated || 0}</p>
                          <p className="text-green-700 text-xs">Signals</p>
                        </div>
                        <div className="flex items-center justify-center text-muted-foreground">
                          <ArrowRight className="h-4 w-4" />
                        </div>
                        <div className="text-center p-2 rounded bg-teal-100">
                          <p className="text-teal-800 font-medium">{funnel.orders_submitted || 0}</p>
                          <p className="text-teal-700 text-xs">Submitted</p>
                        </div>
                        <div className="flex items-center justify-center text-muted-foreground">
                          <ArrowRight className="h-4 w-4" />
                        </div>
                        <div className="text-center p-2 rounded bg-cyan-100">
                          <p className="text-cyan-800 font-medium">{funnel.orders_filled || 0}</p>
                          <p className="text-cyan-700 text-xs">Filled</p>
                        </div>
                      </div>

                      {/* Blocked breakdown */}
                      {((funnel.blocked_pdt || 0) > 0 || (funnel.blocked_risk_validation || 0) > 0 || (funnel.blocked_position_size || 0) > 0) && (
                        <div className="mt-3 pt-3 border-t border-muted">
                          <div className="text-xs text-muted-foreground mb-2">Blocked Signals</div>
                          <div className="flex flex-wrap gap-2 text-xs">
                            {(funnel.blocked_pdt || 0) > 0 && (
                              <span className="px-2 py-1 rounded bg-yellow-100 text-yellow-800">
                                PDT: {funnel.blocked_pdt}
                              </span>
                            )}
                            {(funnel.blocked_risk_validation || 0) > 0 && (
                              <span className="px-2 py-1 rounded bg-red-100 text-red-800">
                                Risk: {funnel.blocked_risk_validation}
                              </span>
                            )}
                            {(funnel.blocked_position_size || 0) > 0 && (
                              <span className="px-2 py-1 rounded bg-orange-100 text-orange-800">
                                Size: {funnel.blocked_position_size}
                              </span>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Risk breakdown details */}
                      {riskBreakdown && Object.keys(riskBreakdown).length > 0 && (
                        <div className="mt-3 pt-3 border-t border-muted">
                          <div className="text-xs text-muted-foreground mb-2">Risk Rejection Details</div>
                          <div className="flex flex-wrap gap-2 text-xs">
                            {Object.entries(riskBreakdown)
                              .filter(([, v]) => v > 0)
                              .map(([reason, count]) => (
                                <span key={reason} className="px-2 py-1 rounded bg-red-50 text-red-700">
                                  {reason.replace(/_/g, ' ')}: {count}
                                </span>
                              ))}
                          </div>
                        </div>
                      )}

                      {/* Trade outcomes */}
                      {(funnel.trades_closed || 0) > 0 && (
                        <div className="mt-3 pt-3 border-t border-muted">
                          <div className="text-xs text-muted-foreground mb-2">Trade Outcomes</div>
                          <div className="flex gap-4 text-sm">
                            <span className="text-green-600 font-medium">
                              Won: {funnel.trades_won || 0}
                            </span>
                            <span className="text-red-600 font-medium">
                              Lost: {funnel.trades_lost || 0}
                            </span>
                            <span className="text-muted-foreground">
                              Win Rate: {((funnel.trades_won || 0) / (funnel.trades_closed || 1) * 100).toFixed(1)}%
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
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
  const { timezone } = useTimezoneStore();

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    }).format(date);
  };

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
                  {formatTime(evaluation.timestamp)}
                </td>
                <td className="px-4 py-2 font-medium">
                  <StrategyTooltip name={evaluation.strategy_name}>{evaluation.strategy_name}</StrategyTooltip>
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

interface FunnelCardProps {
  funnel: FunnelData;
  riskBreakdown?: Record<string, number>;
  totalEvaluations: number;
}

function FunnelCard({ funnel, riskBreakdown, totalEvaluations }: FunnelCardProps) {
  const [showRiskBreakdown, setShowRiskBreakdown] = useState(false);

  // Safely access funnel values with fallback to 0
  const f = {
    skipped_no_data: funnel.skipped_no_data || 0,
    signal_generated: funnel.signal_generated || 0,
    blocked_pdt: funnel.blocked_pdt || 0,
    blocked_risk_validation: funnel.blocked_risk_validation || 0,
    blocked_position_size: funnel.blocked_position_size || 0,
    orders_submitted: funnel.orders_submitted || 0,
    orders_failed: funnel.orders_failed || 0,
    orders_filled: funnel.orders_filled || 0,
    trades_closed: funnel.trades_closed || 0,
    trades_won: funnel.trades_won || 0,
    trades_lost: funnel.trades_lost || 0,
  };

  // Define funnel stages with their values
  const stages = [
    { label: 'Evaluated', value: totalEvaluations, color: 'bg-slate-500' },
    { label: 'Data Available', value: totalEvaluations - f.skipped_no_data, color: 'bg-blue-500' },
    { label: 'Signal Generated', value: f.signal_generated, color: 'bg-green-500' },
    { label: 'Risk Validated', value: f.signal_generated - f.blocked_pdt - f.blocked_risk_validation - f.blocked_position_size, color: 'bg-emerald-500' },
    { label: 'Order Submitted', value: f.orders_submitted, color: 'bg-teal-500' },
    { label: 'Order Filled', value: f.orders_filled, color: 'bg-cyan-500' },
    { label: 'Trade Closed', value: f.trades_closed, color: 'bg-purple-500' },
  ];

  // Filter to only show stages with data or their preceding stages
  const maxStageWithValue = stages.reduce((max, stage, idx) => stage.value > 0 ? idx : max, 0);

  // Calculate rejection summary
  const rejectedAtData = f.skipped_no_data;
  const rejectedAtRisk = f.blocked_pdt + f.blocked_risk_validation + f.blocked_position_size;
  const rejectedAtOrder = f.orders_failed;

  return (
    <div className="rounded-lg border bg-card p-6">
      {/* Funnel Visualization */}
      <div className="space-y-1 mb-6">
        {stages.slice(0, maxStageWithValue + 2).map((stage, idx) => {
          const prevValue = idx > 0 ? stages[idx - 1].value : stage.value;
          const dropoff = prevValue > 0 ? ((prevValue - stage.value) / prevValue * 100) : 0;
          const widthPct = stages[0].value > 0 ? Math.max(5, (stage.value / stages[0].value) * 100) : 5;

          return (
            <div key={stage.label} className="flex items-center gap-3">
              <div className="w-32 text-sm text-right text-muted-foreground">
                {stage.label}
              </div>
              <div className="flex-1 relative">
                <div
                  className={`h-8 ${stage.color} rounded flex items-center justify-end pr-3 transition-all duration-300`}
                  style={{ width: `${widthPct}%` }}
                >
                  <span className="text-white text-sm font-medium">
                    {stage.value.toLocaleString()}
                  </span>
                </div>
              </div>
              <div className="w-20 text-xs text-muted-foreground">
                {idx > 0 && dropoff > 0 && (
                  <span className="text-red-500">-{dropoff.toFixed(1)}%</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Outcome Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t">
        <div className="text-center">
          <p className="text-sm text-muted-foreground">Open Positions</p>
          <p className="text-xl font-bold">{f.orders_filled - f.trades_closed}</p>
        </div>
        <div className="text-center">
          <p className="text-sm text-muted-foreground">Trades Won</p>
          <p className="text-xl font-bold text-green-600">{f.trades_won}</p>
        </div>
        <div className="text-center">
          <p className="text-sm text-muted-foreground">Trades Lost</p>
          <p className="text-xl font-bold text-red-600">{f.trades_lost}</p>
        </div>
        <div className="text-center">
          <p className="text-sm text-muted-foreground">Win Rate</p>
          <p className={`text-xl font-bold ${f.trades_closed > 0 && f.trades_won / f.trades_closed >= 0.5 ? 'text-green-600' : 'text-muted-foreground'}`}>
            {f.trades_closed > 0 ? `${(f.trades_won / f.trades_closed * 100).toFixed(1)}%` : '-'}
          </p>
        </div>
      </div>

      {/* Rejection Breakdown */}
      <div className="mt-4 pt-4 border-t">
        <button
          onClick={() => setShowRiskBreakdown(!showRiskBreakdown)}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          {showRiskBreakdown ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          <AlertTriangle className="h-4 w-4" />
          Rejection Breakdown ({rejectedAtData + rejectedAtRisk + rejectedAtOrder} total blocked)
        </button>

        {showRiskBreakdown && (
          <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div className="rounded bg-muted/50 p-2">
              <p className="text-muted-foreground">No Data</p>
              <p className="font-medium">{f.skipped_no_data.toLocaleString()}</p>
            </div>
            <div className="rounded bg-muted/50 p-2">
              <p className="text-muted-foreground">PDT Blocked</p>
              <p className="font-medium">{f.blocked_pdt.toLocaleString()}</p>
            </div>
            <div className="rounded bg-muted/50 p-2">
              <p className="text-muted-foreground">Risk Validation</p>
              <p className="font-medium">{f.blocked_risk_validation.toLocaleString()}</p>
            </div>
            <div className="rounded bg-muted/50 p-2">
              <p className="text-muted-foreground">Position Size</p>
              <p className="font-medium">{f.blocked_position_size.toLocaleString()}</p>
            </div>

            {/* Risk validation sub-breakdown */}
            {riskBreakdown && Object.entries(riskBreakdown).some(([, v]) => v > 0) && (
              <>
                <div className="col-span-full text-xs text-muted-foreground mt-2">
                  Risk Validation Details:
                </div>
                {Object.entries(riskBreakdown)
                  .filter(([, v]) => v > 0)
                  .map(([reason, count]) => (
                    <div key={reason} className="rounded bg-red-50 p-2">
                      <p className="text-red-700 text-xs">{reason.replace(/_/g, ' ')}</p>
                      <p className="font-medium text-red-800">{count.toLocaleString()}</p>
                    </div>
                  ))}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
