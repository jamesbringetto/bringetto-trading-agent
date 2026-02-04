import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type TimezoneOption = {
  value: string;
  label: string;
  abbrev: string;
};

export const TIMEZONE_OPTIONS: TimezoneOption[] = [
  { value: 'America/New_York', label: 'Eastern Time', abbrev: 'ET' },
  { value: 'America/Chicago', label: 'Central Time', abbrev: 'CT' },
  { value: 'America/Denver', label: 'Mountain Time', abbrev: 'MT' },
  { value: 'America/Los_Angeles', label: 'Pacific Time', abbrev: 'PT' },
  { value: 'UTC', label: 'UTC', abbrev: 'UTC' },
];

interface TimezoneState {
  timezone: string;
  setTimezone: (timezone: string) => void;
}

export const useTimezoneStore = create<TimezoneState>()(
  persist(
    (set) => ({
      timezone: 'America/Los_Angeles', // Default to PST for the user
      setTimezone: (timezone: string) => set({ timezone }),
    }),
    {
      name: 'timezone-storage',
    }
  )
);

/**
 * Get the current timezone option
 */
export function getCurrentTimezoneOption(): TimezoneOption {
  const { timezone } = useTimezoneStore.getState();
  return TIMEZONE_OPTIONS.find((tz) => tz.value === timezone) || TIMEZONE_OPTIONS[0];
}

/**
 * Format a date/time in the selected timezone
 */
export function formatInTimezone(
  value: string | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string {
  if (!value) return '-';

  const { timezone } = useTimezoneStore.getState();
  const date = typeof value === 'string' ? new Date(value) : value;

  const defaultOptions: Intl.DateTimeFormatOptions = {
    timeZone: timezone,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    ...options,
  };

  return new Intl.DateTimeFormat('en-US', defaultOptions).format(date);
}

/**
 * Format time only in the selected timezone
 */
export function formatTimeInTimezone(value: string | Date | null | undefined): string {
  if (!value) return '-';

  const { timezone } = useTimezoneStore.getState();
  const date = typeof value === 'string' ? new Date(value) : value;

  return new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  }).format(date);
}

/**
 * Format date and time in the selected timezone
 */
export function formatDateTimeInTimezone(value: string | Date | null | undefined): string {
  if (!value) return '-';

  const { timezone } = useTimezoneStore.getState();
  const date = typeof value === 'string' ? new Date(value) : value;

  return new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date);
}
