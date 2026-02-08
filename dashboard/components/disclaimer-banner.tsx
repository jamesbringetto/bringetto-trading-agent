import { AlertTriangle } from 'lucide-react';
import Link from 'next/link';

export function DisclaimerBanner() {
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/30 p-3">
      <div className="flex items-start gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
        <div className="text-xs text-amber-800 dark:text-amber-300 leading-relaxed">
          <span className="font-semibold">Not Financial Advice.</span>{' '}
          This application is for educational and experimental purposes only. The creator is not a
          financial advisor, broker, or licensed investment professional. Nothing displayed here
          constitutes financial, investment, or trading advice. Past performance does not guarantee
          future results. See{' '}
          <Link href="/terms" className="underline hover:text-amber-900 dark:hover:text-amber-200">
            Terms of Use
          </Link>{' '}
          for full details.
        </div>
      </div>
    </div>
  );
}
