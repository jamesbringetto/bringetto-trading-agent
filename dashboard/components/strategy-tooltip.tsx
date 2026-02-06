import { getStrategyDescription } from '@/lib/strategy-descriptions';

/**
 * Wraps a strategy name with a hover tooltip showing a brief description.
 * Falls back to rendering children as-is when no description is found.
 */
export function StrategyTooltip({
  name,
  children,
  className,
}: {
  name: string;
  children: React.ReactNode;
  className?: string;
}) {
  const description = getStrategyDescription(name);

  if (!description) {
    return <span className={className}>{children}</span>;
  }

  return (
    <span className={`relative group cursor-help ${className ?? ''}`}>
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-full z-50 mt-1 hidden w-64 rounded-md bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md border group-hover:block"
      >
        {description}
      </span>
    </span>
  );
}
