import { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface StatusCardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon: LucideIcon;
  trend?: 'up' | 'down';
  loading?: boolean;
}

export function StatusCard({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
  loading,
}: StatusCardProps) {
  return (
    <div className="rounded-lg border bg-card p-6">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-muted-foreground">{title}</p>
        <Icon
          className={cn(
            'h-5 w-5',
            trend === 'up' && 'text-green-500',
            trend === 'down' && 'text-red-500',
            !trend && 'text-muted-foreground'
          )}
        />
      </div>
      <div className="mt-2">
        {loading ? (
          <div className="h-8 w-24 animate-pulse rounded bg-muted" />
        ) : (
          <>
            <p
              className={cn(
                'text-2xl font-bold',
                trend === 'up' && 'text-green-600',
                trend === 'down' && 'text-red-600'
              )}
            >
              {value}
            </p>
            {subtitle && (
              <p
                className={cn(
                  'text-sm',
                  trend === 'up' && 'text-green-600',
                  trend === 'down' && 'text-red-600',
                  !trend && 'text-muted-foreground'
                )}
              >
                {subtitle}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
