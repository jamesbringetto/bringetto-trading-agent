'use client';

import { useQuery } from '@tanstack/react-query';
import { api, Trade } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

export function RecentTrades() {
  const { data: trades, isLoading } = useQuery({
    queryKey: ['trades'],
    queryFn: () => api.getTrades(10),
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-16 animate-pulse rounded bg-muted" />
        ))}
      </div>
    );
  }

  if (!trades?.length) {
    return (
      <p className="text-center text-muted-foreground py-8">
        No trades yet. The agent will start trading during market hours.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm min-w-[550px]">
        <thead>
          <tr className="border-b text-left text-sm text-muted-foreground">
            <th className="pb-3 font-medium">Symbol</th>
            <th className="pb-3 font-medium">Side</th>
            <th className="pb-3 font-medium">Strategy</th>
            <th className="pb-3 font-medium">Entry</th>
            <th className="pb-3 font-medium">Exit</th>
            <th className="pb-3 font-medium text-right">P&L</th>
            <th className="pb-3 font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="text-sm">
          {trades.map((trade) => (
            <TradeRow key={trade.id} trade={trade} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradeRow({ trade }: { trade: Trade }) {
  const isBuy = trade.side === 'buy';
  const isOpen = trade.status === 'open';

  return (
    <tr className="border-b last:border-0">
      <td className="py-3">
        <div className="flex items-center gap-2">
          {isBuy ? (
            <ArrowUpRight className="h-4 w-4 text-green-500" />
          ) : (
            <ArrowDownRight className="h-4 w-4 text-red-500" />
          )}
          <span className="font-medium">{trade.symbol}</span>
        </div>
      </td>
      <td className="py-3">
        <span
          className={`px-2 py-0.5 rounded text-xs font-medium ${
            isBuy ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
          }`}
        >
          {trade.side.toUpperCase()}
        </span>
      </td>
      <td className="py-3 text-muted-foreground">{trade.strategy_name}</td>
      <td className="py-3">{formatCurrency(trade.entry_price)}</td>
      <td className="py-3">
        {trade.exit_price ? formatCurrency(trade.exit_price) : '-'}
      </td>
      <td className="py-3 text-right">
        {trade.pnl !== null ? (
          <div className="flex flex-col items-end">
            <span
              className={`font-medium ${
                trade.pnl >= 0 ? 'text-green-600' : 'text-red-600'
              }`}
            >
              {formatCurrency(trade.pnl)}
            </span>
            {isOpen && (
              <span className="text-xs text-muted-foreground">unrealized</span>
            )}
          </div>
        ) : (
          '-'
        )}
      </td>
      <td className="py-3">
        <span
          className={`px-2 py-0.5 rounded text-xs ${
            isOpen
              ? 'bg-blue-100 text-blue-700'
              : 'bg-gray-100 text-gray-700'
          }`}
        >
          {trade.status}
        </span>
      </td>
    </tr>
  );
}
