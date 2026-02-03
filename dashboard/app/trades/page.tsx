'use client';

import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

export default function TradesPage() {
  const { data: trades, isLoading } = useQuery({
    queryKey: ['allTrades'],
    queryFn: () => api.getTrades(100),
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Trade History</h1>
        <div className="animate-pulse space-y-2">
          {[...Array(10)].map((_, i) => (
            <div key={i} className="h-12 bg-muted rounded" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Trade History</h1>
        <p className="text-muted-foreground">
          Complete history of all trades executed by the agent
        </p>
      </div>

      <div className="rounded-lg border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b text-left text-sm text-muted-foreground">
                <th className="p-4 font-medium">Time</th>
                <th className="p-4 font-medium">Symbol</th>
                <th className="p-4 font-medium">Side</th>
                <th className="p-4 font-medium">Strategy</th>
                <th className="p-4 font-medium">Qty</th>
                <th className="p-4 font-medium">Entry</th>
                <th className="p-4 font-medium">Exit</th>
                <th className="p-4 font-medium text-right">P&L</th>
                <th className="p-4 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="text-sm">
              {trades?.map((trade) => (
                <tr key={trade.id} className="border-b last:border-0 hover:bg-muted/50">
                  <td className="p-4 text-muted-foreground">
                    {new Date(trade.entry_time).toLocaleString()}
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-2">
                      {trade.side === 'buy' ? (
                        <ArrowUpRight className="h-4 w-4 text-green-500" />
                      ) : (
                        <ArrowDownRight className="h-4 w-4 text-red-500" />
                      )}
                      <span className="font-medium">{trade.symbol}</span>
                    </div>
                  </td>
                  <td className="p-4">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium ${
                        trade.side === 'buy'
                          ? 'bg-green-100 text-green-700'
                          : 'bg-red-100 text-red-700'
                      }`}
                    >
                      {trade.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="p-4 text-muted-foreground">{trade.strategy_name}</td>
                  <td className="p-4">{trade.quantity}</td>
                  <td className="p-4">{formatCurrency(trade.entry_price)}</td>
                  <td className="p-4">
                    {trade.exit_price ? formatCurrency(trade.exit_price) : '-'}
                  </td>
                  <td className="p-4 text-right">
                    {trade.pnl !== null ? (
                      <span
                        className={`font-medium ${
                          trade.pnl >= 0 ? 'text-green-600' : 'text-red-600'
                        }`}
                      >
                        {formatCurrency(trade.pnl)}
                      </span>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td className="p-4">
                    <span
                      className={`px-2 py-0.5 rounded text-xs ${
                        trade.status === 'open'
                          ? 'bg-blue-100 text-blue-700'
                          : trade.status === 'closed'
                          ? 'bg-gray-100 text-gray-700'
                          : 'bg-yellow-100 text-yellow-700'
                      }`}
                    >
                      {trade.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!trades?.length && (
          <div className="p-8 text-center text-muted-foreground">
            No trades yet. The agent will start trading during market hours.
          </div>
        )}
      </div>
    </div>
  );
}
