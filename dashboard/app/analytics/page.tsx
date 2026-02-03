'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
  Legend,
  Area,
  AreaChart,
} from 'recharts';
import {
  BarChart3,
  TrendingUp,
  Clock,
  Target,
  AlertTriangle,
  DollarSign,
  Percent,
  Activity,
} from 'lucide-react';
import { api } from '@/lib/api';
import { formatCurrency, formatPercent, formatDuration, cn } from '@/lib/utils';

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);

  const { data: pnlCurve, isLoading: pnlLoading } = useQuery({
    queryKey: ['pnlCurve', days],
    queryFn: () => api.getPnLCurve(days),
  });

  const { data: timeOfDay, isLoading: todLoading } = useQuery({
    queryKey: ['timeOfDay', days],
    queryFn: () => api.getTimeOfDayPerformance(days),
  });

  const { data: symbolPerf, isLoading: symbolLoading } = useQuery({
    queryKey: ['symbolPerf', days],
    queryFn: () => api.getSymbolPerformance(days, 10),
  });

  const { data: strategyComp, isLoading: strategyLoading } = useQuery({
    queryKey: ['strategyComp', days],
    queryFn: () => api.getStrategyComparison(days),
  });

  const { data: riskMetrics, isLoading: riskLoading } = useQuery({
    queryKey: ['riskMetrics', days],
    queryFn: () => api.getRiskMetrics(days),
  });

  const { data: distribution, isLoading: distLoading } = useQuery({
    queryKey: ['distribution', days],
    queryFn: () => api.getTradeDistribution(days),
  });

  const hasData =
    (pnlCurve && pnlCurve.length > 0) ||
    (timeOfDay && timeOfDay.length > 0) ||
    (symbolPerf && symbolPerf.length > 0) ||
    (strategyComp && strategyComp.length > 0);

  const isLoading =
    pnlLoading || todLoading || symbolLoading || strategyLoading || riskLoading || distLoading;

  // Format hour for display
  const formatHour = (hour: number) => {
    if (hour === 0) return '12 AM';
    if (hour === 12) return '12 PM';
    if (hour < 12) return `${hour} AM`;
    return `${hour - 12} PM`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Analytics</h1>
          <p className="text-muted-foreground">
            Deep dive into your trading performance
          </p>
        </div>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="rounded-md border bg-background px-3 py-2 text-sm"
        >
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
          <option value={365}>Last year</option>
        </select>
      </div>

      {/* Risk Metrics Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title="Win Rate"
          value={riskMetrics?.win_rate ? `${riskMetrics.win_rate.toFixed(1)}%` : '-'}
          icon={Target}
          loading={riskLoading}
          good={riskMetrics?.win_rate ? riskMetrics.win_rate >= 55 : undefined}
        />
        <MetricCard
          title="Profit Factor"
          value={riskMetrics?.profit_factor ? riskMetrics.profit_factor.toFixed(2) : '-'}
          icon={TrendingUp}
          loading={riskLoading}
          good={riskMetrics?.profit_factor ? riskMetrics.profit_factor >= 1.5 : undefined}
        />
        <MetricCard
          title="Sharpe Ratio"
          value={riskMetrics?.sharpe_ratio ? riskMetrics.sharpe_ratio.toFixed(2) : '-'}
          icon={Activity}
          loading={riskLoading}
          good={riskMetrics?.sharpe_ratio ? riskMetrics.sharpe_ratio >= 1.0 : undefined}
        />
        <MetricCard
          title="Max Drawdown"
          value={riskMetrics?.max_drawdown ? formatCurrency(riskMetrics.max_drawdown) : '-'}
          icon={AlertTriangle}
          loading={riskLoading}
          good={
            riskMetrics?.max_drawdown
              ? Math.abs(riskMetrics.max_drawdown) < 10000
              : undefined
          }
        />
      </div>

      {/* Second Row of Metrics */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title="Avg Win"
          value={riskMetrics?.avg_win ? formatCurrency(riskMetrics.avg_win) : '-'}
          icon={DollarSign}
          loading={riskLoading}
        />
        <MetricCard
          title="Avg Loss"
          value={riskMetrics?.avg_loss ? formatCurrency(-riskMetrics.avg_loss) : '-'}
          icon={DollarSign}
          loading={riskLoading}
        />
        <MetricCard
          title="Expectancy"
          value={riskMetrics?.expectancy ? formatCurrency(riskMetrics.expectancy) : '-'}
          icon={Percent}
          loading={riskLoading}
          good={riskMetrics?.expectancy ? riskMetrics.expectancy > 0 : undefined}
        />
        <MetricCard
          title="Risk/Reward"
          value={riskMetrics?.risk_reward_ratio ? `1:${riskMetrics.risk_reward_ratio.toFixed(1)}` : '-'}
          icon={Target}
          loading={riskLoading}
          good={riskMetrics?.risk_reward_ratio ? riskMetrics.risk_reward_ratio >= 1.5 : undefined}
        />
      </div>

      {!hasData && !isLoading ? (
        <div className="rounded-lg border bg-card p-12 text-center">
          <BarChart3 className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <h2 className="text-lg font-semibold mb-2">No Trading Data Yet</h2>
          <p className="text-muted-foreground max-w-md mx-auto">
            Once you have executed trades, this page will show detailed analytics including
            P&L curves, win rates by time of day, symbol performance, and more.
          </p>
        </div>
      ) : (
        <>
          {/* P&L Curve */}
          <div className="rounded-lg border bg-card p-6">
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp className="h-5 w-5 text-muted-foreground" />
              <h2 className="text-lg font-semibold">Cumulative P&L</h2>
            </div>
            {pnlCurve && pnlCurve.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={pnlCurve}>
                  <defs>
                    <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#16a34a" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#16a34a" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(value) =>
                      new Date(value).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                      })
                    }
                    tick={{ fontSize: 12 }}
                  />
                  <YAxis
                    tickFormatter={(value) => `$${value.toLocaleString()}`}
                    tick={{ fontSize: 12 }}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        return (
                          <div className="rounded-lg border bg-card p-3 shadow-lg">
                            <p className="text-sm text-muted-foreground">
                              {new Date(data.date).toLocaleDateString()}
                            </p>
                            <p className="font-semibold">
                              Cumulative: {formatCurrency(data.cumulative_pnl)}
                            </p>
                            <p className="text-sm">Daily: {formatCurrency(data.daily_pnl)}</p>
                            <p className="text-sm text-muted-foreground">
                              {data.trade_count} trades
                            </p>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="cumulative_pnl"
                    stroke="#16a34a"
                    fill="url(#pnlGradient)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                No P&L data available
              </div>
            )}
          </div>

          {/* Two Column Charts */}
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Win Rate by Time of Day */}
            <div className="rounded-lg border bg-card p-6">
              <div className="flex items-center gap-2 mb-4">
                <Clock className="h-5 w-5 text-muted-foreground" />
                <h2 className="text-lg font-semibold">Win Rate by Time of Day</h2>
              </div>
              {timeOfDay && timeOfDay.length > 0 ? (
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={timeOfDay.filter((t) => t.total_trades > 0)}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis
                      dataKey="hour"
                      tickFormatter={formatHour}
                      tick={{ fontSize: 11 }}
                    />
                    <YAxis
                      tickFormatter={(value) => `${value}%`}
                      domain={[0, 100]}
                      tick={{ fontSize: 12 }}
                    />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const data = payload[0].payload;
                          return (
                            <div className="rounded-lg border bg-card p-3 shadow-lg">
                              <p className="font-semibold">{formatHour(data.hour)}</p>
                              <p className="text-sm">
                                Win Rate:{' '}
                                <span className={data.win_rate >= 55 ? 'text-green-600' : 'text-red-600'}>
                                  {data.win_rate?.toFixed(1)}%
                                </span>
                              </p>
                              <p className="text-sm">Trades: {data.total_trades}</p>
                              <p className="text-sm">P&L: {formatCurrency(data.total_pnl)}</p>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                    <Bar dataKey="win_rate" radius={[4, 4, 0, 0]}>
                      {timeOfDay
                        .filter((t) => t.total_trades > 0)
                        .map((entry, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={entry.win_rate && entry.win_rate >= 55 ? '#16a34a' : '#dc2626'}
                          />
                        ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[250px] flex items-center justify-center text-muted-foreground">
                  No time-of-day data available
                </div>
              )}
            </div>

            {/* P&L Distribution */}
            <div className="rounded-lg border bg-card p-6">
              <div className="flex items-center gap-2 mb-4">
                <BarChart3 className="h-5 w-5 text-muted-foreground" />
                <h2 className="text-lg font-semibold">P&L Distribution</h2>
              </div>
              {distribution?.pnl_ranges && distribution.pnl_ranges.length > 0 ? (
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={distribution.pnl_ranges.filter((r) => r.count > 0)}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis dataKey="range" tick={{ fontSize: 10 }} angle={-45} textAnchor="end" height={60} />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const data = payload[0].payload;
                          return (
                            <div className="rounded-lg border bg-card p-3 shadow-lg">
                              <p className="font-semibold">{data.range}</p>
                              <p className="text-sm">{data.count} trades</p>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                    <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[250px] flex items-center justify-center text-muted-foreground">
                  No distribution data available
                </div>
              )}
            </div>
          </div>

          {/* Strategy Comparison Table */}
          <div className="rounded-lg border bg-card p-6">
            <h2 className="text-lg font-semibold mb-4">Strategy Comparison</h2>
            {strategyComp && strategyComp.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-3 px-2 font-medium">Strategy</th>
                      <th className="text-right py-3 px-2 font-medium">Status</th>
                      <th className="text-right py-3 px-2 font-medium">Trades</th>
                      <th className="text-right py-3 px-2 font-medium">Win Rate</th>
                      <th className="text-right py-3 px-2 font-medium">P&L</th>
                      <th className="text-right py-3 px-2 font-medium">Profit Factor</th>
                      <th className="text-right py-3 px-2 font-medium">Sharpe</th>
                      <th className="text-right py-3 px-2 font-medium">Max DD</th>
                      <th className="text-right py-3 px-2 font-medium">Avg Hold Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {strategyComp.map((s) => (
                      <tr key={s.name} className="border-b hover:bg-muted/50">
                        <td className="py-3 px-2">
                          <div>
                            <p className="font-medium">{s.name}</p>
                            <p className="text-xs text-muted-foreground">{s.strategy_type}</p>
                          </div>
                        </td>
                        <td className="text-right py-3 px-2">
                          <span
                            className={cn(
                              'text-xs px-2 py-0.5 rounded',
                              s.is_active
                                ? 'bg-green-100 text-green-700'
                                : 'bg-red-100 text-red-700'
                            )}
                          >
                            {s.is_active ? 'Active' : 'Disabled'}
                          </span>
                        </td>
                        <td className="text-right py-3 px-2">{s.total_trades}</td>
                        <td className="text-right py-3 px-2">
                          <span
                            className={
                              s.win_rate && s.win_rate >= 55
                                ? 'text-green-600'
                                : 'text-red-600'
                            }
                          >
                            {s.win_rate?.toFixed(1)}%
                          </span>
                        </td>
                        <td className="text-right py-3 px-2">
                          <span className={s.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'}>
                            {formatCurrency(s.total_pnl)}
                          </span>
                        </td>
                        <td className="text-right py-3 px-2">
                          <span
                            className={
                              s.profit_factor && s.profit_factor >= 1.5
                                ? 'text-green-600'
                                : s.profit_factor && s.profit_factor >= 1.0
                                ? 'text-yellow-600'
                                : 'text-red-600'
                            }
                          >
                            {s.profit_factor?.toFixed(2) || '-'}
                          </span>
                        </td>
                        <td className="text-right py-3 px-2">
                          {s.sharpe_ratio?.toFixed(2) || '-'}
                        </td>
                        <td className="text-right py-3 px-2 text-red-600">
                          {s.max_drawdown ? formatCurrency(s.max_drawdown) : '-'}
                        </td>
                        <td className="text-right py-3 px-2 text-muted-foreground">
                          {s.avg_holding_time_seconds
                            ? formatDuration(Math.round(s.avg_holding_time_seconds))
                            : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-center text-muted-foreground py-8">
                No strategy comparison data available
              </p>
            )}
          </div>

          {/* Symbol Performance Table */}
          <div className="rounded-lg border bg-card p-6">
            <h2 className="text-lg font-semibold mb-4">Symbol Performance</h2>
            {symbolPerf && symbolPerf.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-3 px-2 font-medium">Symbol</th>
                      <th className="text-right py-3 px-2 font-medium">Trades</th>
                      <th className="text-right py-3 px-2 font-medium">Win Rate</th>
                      <th className="text-right py-3 px-2 font-medium">Total P&L</th>
                      <th className="text-right py-3 px-2 font-medium">Avg P&L</th>
                      <th className="text-right py-3 px-2 font-medium">Best Trade</th>
                      <th className="text-right py-3 px-2 font-medium">Worst Trade</th>
                    </tr>
                  </thead>
                  <tbody>
                    {symbolPerf.map((s) => (
                      <tr key={s.symbol} className="border-b hover:bg-muted/50">
                        <td className="py-3 px-2 font-medium">{s.symbol}</td>
                        <td className="text-right py-3 px-2">{s.total_trades}</td>
                        <td className="text-right py-3 px-2">
                          <span
                            className={
                              s.win_rate && s.win_rate >= 55
                                ? 'text-green-600'
                                : 'text-red-600'
                            }
                          >
                            {s.win_rate?.toFixed(1)}%
                          </span>
                        </td>
                        <td className="text-right py-3 px-2">
                          <span className={s.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'}>
                            {formatCurrency(s.total_pnl)}
                          </span>
                        </td>
                        <td className="text-right py-3 px-2">
                          <span
                            className={
                              s.avg_pnl && s.avg_pnl >= 0 ? 'text-green-600' : 'text-red-600'
                            }
                          >
                            {s.avg_pnl ? formatCurrency(s.avg_pnl) : '-'}
                          </span>
                        </td>
                        <td className="text-right py-3 px-2 text-green-600">
                          {s.largest_win ? formatCurrency(s.largest_win) : '-'}
                        </td>
                        <td className="text-right py-3 px-2 text-red-600">
                          {s.largest_loss ? formatCurrency(s.largest_loss) : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-center text-muted-foreground py-8">
                No symbol performance data available
              </p>
            )}
          </div>

          {/* Trade Side Distribution */}
          {distribution?.side_distribution && (
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="rounded-lg border bg-card p-6">
                <h2 className="text-lg font-semibold mb-4">Trade Direction</h2>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie
                      data={[
                        { name: 'Buy', value: distribution.side_distribution.buy },
                        { name: 'Sell', value: distribution.side_distribution.sell },
                      ]}
                      cx="50%"
                      cy="50%"
                      innerRadius={40}
                      outerRadius={80}
                      paddingAngle={5}
                      dataKey="value"
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    >
                      <Cell fill="#16a34a" />
                      <Cell fill="#dc2626" />
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              <div className="rounded-lg border bg-card p-6">
                <h2 className="text-lg font-semibold mb-4">Holding Time Distribution</h2>
                {distribution.holding_time_distribution && distribution.holding_time_distribution.length > 0 ? (
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={distribution.holding_time_distribution.filter((h) => h.count > 0)}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                      <XAxis dataKey="range" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 12 }} />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (active && payload && payload.length) {
                            const data = payload[0].payload;
                            return (
                              <div className="rounded-lg border bg-card p-3 shadow-lg">
                                <p className="font-semibold">{data.range}</p>
                                <p className="text-sm">{data.count} trades</p>
                              </div>
                            );
                          }
                          return null;
                        }}
                      />
                      <Bar dataKey="count" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-[200px] flex items-center justify-center text-muted-foreground">
                    No holding time data
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// Metric card component
function MetricCard({
  title,
  value,
  icon: Icon,
  loading,
  good,
}: {
  title: string;
  value: string;
  icon: React.ElementType;
  loading?: boolean;
  good?: boolean;
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-muted-foreground">{title}</span>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      {loading ? (
        <div className="h-8 w-24 bg-muted animate-pulse rounded" />
      ) : (
        <p
          className={cn(
            'text-2xl font-bold',
            good === true && 'text-green-600',
            good === false && 'text-red-600'
          )}
        >
          {value}
        </p>
      )}
      {good !== undefined && (
        <p className={cn('text-xs mt-1', good ? 'text-green-600' : 'text-red-600')}>
          {good ? 'Meeting target' : 'Below target'}
        </p>
      )}
    </div>
  );
}
