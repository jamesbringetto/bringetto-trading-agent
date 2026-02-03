'use client';

import { BarChart3 } from 'lucide-react';

export default function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Analytics</h1>
        <p className="text-muted-foreground">
          Deep dive into your trading performance
        </p>
      </div>

      <div className="rounded-lg border bg-card p-12 text-center">
        <BarChart3 className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
        <h2 className="text-lg font-semibold mb-2">Analytics Coming Soon</h2>
        <p className="text-muted-foreground max-w-md mx-auto">
          Once you have enough trades (50+), this page will show detailed analytics including:
        </p>
        <ul className="mt-4 text-sm text-muted-foreground space-y-1">
          <li>P&L curves over time</li>
          <li>Win rate by time of day</li>
          <li>Best/worst performing symbols</li>
          <li>Strategy comparison charts</li>
          <li>Risk metrics (Sharpe ratio, max drawdown)</li>
          <li>A/B test results</li>
        </ul>
      </div>
    </div>
  );
}
