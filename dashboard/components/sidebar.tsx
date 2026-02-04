'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  TrendingUp,
  History,
  Settings,
  AlertTriangle,
  BarChart3,
  Activity,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { TimezoneSelector } from './timezone-selector';

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Strategies', href: '/strategies', icon: TrendingUp },
  { name: 'Trades', href: '/trades', icon: History },
  { name: 'Analytics', href: '/analytics', icon: BarChart3 },
  { name: 'Instrumentation', href: '/instrumentation', icon: Activity },
  { name: 'Settings', href: '/settings', icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="flex h-full w-64 flex-col bg-card border-r">
      {/* Header */}
      <div className="flex h-16 items-center border-b px-6">
        <TrendingUp className="h-6 w-6 text-primary mr-2" />
        <span className="text-lg font-semibold">Bringetto</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-4">
        {navigation.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* Kill Switch */}
      <div className="border-t p-4">
        <button className="flex w-full items-center justify-center gap-2 rounded-lg bg-destructive px-3 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors">
          <AlertTriangle className="h-4 w-4" />
          Kill Switch
        </button>
      </div>

      {/* Timezone Selector */}
      <div className="border-t px-4 py-3">
        <TimezoneSelector />
      </div>

      {/* Legal Links */}
      <div className="border-t px-4 py-3">
        <div className="flex justify-center gap-3 text-xs text-muted-foreground">
          <Link href="/terms" className="hover:text-foreground hover:underline">
            Terms
          </Link>
          <span>|</span>
          <Link href="/privacy" className="hover:text-foreground hover:underline">
            Privacy
          </Link>
        </div>
      </div>
    </div>
  );
}
