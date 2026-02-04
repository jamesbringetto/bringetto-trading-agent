'use client';

import { useQuery } from '@tanstack/react-query';
import { api, MarketStatus as MarketStatusType } from '@/lib/api';
import { cn } from '@/lib/utils';
import {
  Clock,
  Sun,
  Moon,
  Sunrise,
  Sunset,
  RefreshCw,
} from 'lucide-react';

const SESSION_CONFIG = {
  overnight: {
    icon: Moon,
    color: 'text-indigo-500',
    bgColor: 'bg-indigo-500/10',
    borderColor: 'border-indigo-500/30',
  },
  pre_market: {
    icon: Sunrise,
    color: 'text-orange-500',
    bgColor: 'bg-orange-500/10',
    borderColor: 'border-orange-500/30',
  },
  regular: {
    icon: Sun,
    color: 'text-green-500',
    bgColor: 'bg-green-500/10',
    borderColor: 'border-green-500/30',
  },
  after_hours: {
    icon: Sunset,
    color: 'text-amber-500',
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-amber-500/30',
  },
  unknown: {
    icon: Clock,
    color: 'text-gray-500',
    bgColor: 'bg-gray-500/10',
    borderColor: 'border-gray-500/30',
  },
};

function formatTime(isoString: string | null): string {
  if (!isoString) return '-';
  try {
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short',
    });
  } catch {
    return '-';
  }
}

export function MarketStatusWidget() {
  const {
    data: status,
    isLoading,
    error,
    refetch,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ['marketStatus'],
    queryFn: api.getMarketStatus,
    refetchInterval: 30000, // Refresh every 30 seconds
    staleTime: 10000, // Consider data stale after 10 seconds
  });

  const session = status?.current_session || 'unknown';
  const config = SESSION_CONFIG[session] || SESSION_CONFIG.unknown;
  const Icon = config.icon;

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString()
    : '-';

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-red-500" />
            <span className="font-medium text-red-500">Market Status Error</span>
          </div>
          <button
            onClick={() => refetch()}
            className="text-red-500 hover:text-red-400"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-2 text-sm text-red-400">Unable to fetch market status</p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'rounded-lg border p-4 transition-all',
        config.bgColor,
        config.borderColor
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'flex h-10 w-10 items-center justify-center rounded-full',
              config.bgColor
            )}
          >
            {isLoading ? (
              <RefreshCw className={cn('h-5 w-5 animate-spin', config.color)} />
            ) : (
              <Icon className={cn('h-5 w-5', config.color)} />
            )}
          </div>
          <div>
            <h3 className="font-semibold">Market Status</h3>
            <p className={cn('text-sm font-medium', config.color)}>
              {isLoading ? 'Loading...' : status?.session_display || 'Unknown'}
            </p>
          </div>
        </div>

        {/* Live indicator */}
        <div className="flex items-center gap-2">
          <div
            className={cn(
              'h-2 w-2 rounded-full',
              status?.is_open ? 'bg-green-500 animate-pulse' : 'bg-gray-400'
            )}
          />
          <span className="text-xs text-muted-foreground">
            {status?.is_open ? 'Open' : 'Closed'}
          </span>
        </div>
      </div>

      {/* Session times */}
      {!isLoading && status && (
        <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground">Next Open</p>
            <p className="font-medium">{formatTime(status.next_open)}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Next Close</p>
            <p className="font-medium">{formatTime(status.next_close)}</p>
          </div>
        </div>
      )}

      {/* Trading availability */}
      {!isLoading && status && (
        <div className="mt-4 flex flex-wrap gap-2">
          <TradingBadge
            label="Regular"
            available={status.can_trade_regular}
          />
          <TradingBadge
            label="Extended"
            available={status.can_trade_extended}
          />
          <TradingBadge
            label="Overnight"
            available={status.can_trade_overnight}
          />
        </div>
      )}

      {/* Last updated */}
      <div className="mt-3 flex items-center justify-between border-t border-border/50 pt-3">
        <span className="text-xs text-muted-foreground">
          Updated: {lastUpdated}
        </span>
        <button
          onClick={() => refetch()}
          className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
          disabled={isLoading}
        >
          <RefreshCw className={cn('h-3 w-3', isLoading && 'animate-spin')} />
          Refresh
        </button>
      </div>
    </div>
  );
}

function TradingBadge({
  label,
  available,
}: {
  label: string;
  available: boolean;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        available
          ? 'bg-green-500/10 text-green-500'
          : 'bg-gray-500/10 text-gray-500'
      )}
    >
      <span
        className={cn(
          'mr-1.5 h-1.5 w-1.5 rounded-full',
          available ? 'bg-green-500' : 'bg-gray-400'
        )}
      />
      {label}
    </span>
  );
}
