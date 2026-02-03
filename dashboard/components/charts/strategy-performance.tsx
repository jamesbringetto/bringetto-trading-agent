'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { StrategyPerformance } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';

interface StrategyPerformanceChartProps {
  strategies: StrategyPerformance[];
}

export function StrategyPerformanceChart({
  strategies,
}: StrategyPerformanceChartProps) {
  const data = strategies.map((s) => ({
    name: s.name.replace(' Strategy', '').replace('Opening Range ', ''),
    pnl: s.total_pnl,
    winRate: s.win_rate,
    trades: s.total_trades,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis
          dataKey="name"
          tick={{ fontSize: 12 }}
          className="text-muted-foreground"
        />
        <YAxis
          tickFormatter={(value) => `$${value}`}
          tick={{ fontSize: 12 }}
          className="text-muted-foreground"
        />
        <Tooltip
          content={({ active, payload }) => {
            if (active && payload && payload.length) {
              const data = payload[0].payload;
              return (
                <div className="rounded-lg border bg-card p-3 shadow-lg">
                  <p className="font-semibold">{data.name}</p>
                  <p className="text-sm">
                    P&L:{' '}
                    <span
                      className={
                        data.pnl >= 0 ? 'text-green-600' : 'text-red-600'
                      }
                    >
                      {formatCurrency(data.pnl)}
                    </span>
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Win Rate: {data.winRate.toFixed(1)}%
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Trades: {data.trades}
                  </p>
                </div>
              );
            }
            return null;
          }}
        />
        <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => (
            <Cell
              key={`cell-${index}`}
              fill={entry.pnl >= 0 ? '#16a34a' : '#dc2626'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
