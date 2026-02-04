'use client';

import { Globe } from 'lucide-react';
import { useTimezoneStore, TIMEZONE_OPTIONS } from '@/lib/timezone-store';

export function TimezoneSelector() {
  const { timezone, setTimezone } = useTimezoneStore();

  const currentOption = TIMEZONE_OPTIONS.find((tz) => tz.value === timezone);

  return (
    <div className="flex items-center gap-2">
      <Globe className="h-4 w-4 text-muted-foreground" />
      <select
        value={timezone}
        onChange={(e) => setTimezone(e.target.value)}
        className="bg-transparent text-sm text-muted-foreground hover:text-foreground cursor-pointer focus:outline-none focus:ring-1 focus:ring-primary rounded px-1 py-0.5"
        title="Select timezone"
      >
        {TIMEZONE_OPTIONS.map((tz) => (
          <option key={tz.value} value={tz.value}>
            {tz.abbrev} - {tz.label}
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * Compact version for use in tight spaces
 */
export function TimezoneLabel() {
  const { timezone } = useTimezoneStore();
  const currentOption = TIMEZONE_OPTIONS.find((tz) => tz.value === timezone);

  return (
    <span className="text-xs text-muted-foreground">
      {currentOption?.abbrev || 'ET'}
    </span>
  );
}
