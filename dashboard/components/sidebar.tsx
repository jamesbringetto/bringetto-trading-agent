'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  TrendingUp,
  History,
  Settings,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { TimezoneSelector } from './timezone-selector';

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Trades', href: '/trades', icon: History },
  { name: 'Settings', href: '/settings', icon: Settings },
];

interface SidebarProps {
  onNavigate?: () => void;
}

export function Sidebar({ onNavigate }: SidebarProps) {
  const pathname = usePathname();

  return (
    <div className="flex h-full w-64 flex-col bg-card border-r">
      {/* Header */}
      <div className="flex h-16 items-center border-b px-6 justify-between">
        <div className="flex items-center">
          <TrendingUp className="h-6 w-6 text-primary mr-2" />
          <span className="text-lg font-semibold">Bringetto</span>
        </div>
        {/* Close button - mobile only */}
        <button
          onClick={onNavigate}
          className="md:hidden p-1 rounded-md hover:bg-muted transition-colors"
          aria-label="Close menu"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-4">
        {navigation.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              onClick={onNavigate}
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

      {/* Timezone Selector */}
      <div className="border-t px-4 py-3">
        <TimezoneSelector />
      </div>

      {/* Legal Links */}
      <div className="border-t px-4 py-3">
        <p className="text-[10px] text-muted-foreground text-center mb-2">
          Not financial advice. For educational purposes only.
        </p>
        <div className="flex justify-center gap-3 text-xs text-muted-foreground">
          <Link href="/terms" onClick={onNavigate} className="hover:text-foreground hover:underline">
            Terms
          </Link>
          <span>|</span>
          <Link href="/privacy" onClick={onNavigate} className="hover:text-foreground hover:underline">
            Privacy
          </Link>
          <span>|</span>
          <Link href="/disclaimer" onClick={onNavigate} className="hover:text-foreground hover:underline">
            Disclaimer
          </Link>
        </div>
      </div>
    </div>
  );
}
