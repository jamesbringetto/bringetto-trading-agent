import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Disclaimer | Bringetto Trading Agent',
  description: 'Legal disclaimer for Bringetto Trading Agent',
};

export default function DisclaimerPage() {
  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-3xl mx-auto py-12 px-6">
        <div className="mb-8">
          <Link
            href="/"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            &larr; Back to Dashboard
          </Link>
        </div>

        <h1 className="text-3xl font-bold mb-2">Disclaimer</h1>
        <p className="text-muted-foreground mb-8">Last updated: February 2026</p>

        <div className="prose prose-neutral dark:prose-invert max-w-none space-y-6">
          <section className="rounded-lg border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/30 p-6">
            <h2 className="text-xl font-semibold mb-3 text-amber-900 dark:text-amber-200">
              Important Notice
            </h2>
            <p className="text-amber-800 dark:text-amber-300 leading-relaxed font-medium">
              The creator of Bringetto Trading Agent is not a financial advisor, broker, dealer,
              or licensed investment professional. The creator has no formal qualifications in
              finance, investment management, or securities trading. This application was built
              as a personal educational and experimental project. Nothing in this application
              constitutes financial, investment, tax, or legal advice.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">Not Financial Advice</h2>
            <p className="text-muted-foreground leading-relaxed">
              This application, including all trading strategies, signals, analysis, performance
              metrics, and data displayed on the dashboard and provided through the API, is for
              educational and experimental purposes only. The information presented should not be
              construed as a recommendation to buy, sell, or hold any security or financial
              instrument. You should not make any investment decisions based on the information
              provided by this application. Always consult with qualified financial, legal, and
              tax professionals before making investment decisions.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">No Warranties</h2>
            <p className="text-muted-foreground leading-relaxed">
              This software is provided &quot;as is&quot; and &quot;as available&quot; without
              warranties of any kind, either express or implied. There is no guarantee that the
              software will operate without errors, that trading strategies will be profitable,
              that market data or calculations are accurate, or that the software is suitable for
              any particular purpose.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">No Liability for Losses</h2>
            <p className="text-muted-foreground leading-relaxed">
              The creator shall not be held liable for any financial losses, damages, or other
              negative outcomes resulting from the use of this software, including but not limited
              to: losses from trades executed by the automated trading agent, losses from decisions
              made based on data displayed by the dashboard, losses from software bugs or system
              failures, and losses from reliance on backtesting or paper trading results.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">Paper Trading</h2>
            <p className="text-muted-foreground leading-relaxed">
              This application is configured for paper trading (simulated trading with virtual
              money) through Alpaca Markets&apos; paper trading environment. Paper trading results
              do not reflect real market conditions such as slippage, partial fills, or real
              liquidity constraints. Paper trading results should not be used as an indicator of
              potential real-money trading performance.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">Past Performance</h2>
            <p className="text-muted-foreground leading-relaxed">
              Past performance of any trading strategy, whether in paper trading, backtesting, or
              any other simulated or real environment, does not guarantee future results. Markets
              are inherently unpredictable, and historical patterns may not repeat. Any performance
              metrics displayed by this application are historical in nature and should not be
              interpreted as predictive of future performance.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">Third-Party Services</h2>
            <p className="text-muted-foreground leading-relaxed">
              This software integrates with third-party services including{' '}
              <a
                href="https://alpaca.markets"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                Alpaca Markets
              </a>
              . The creator is not affiliated with, endorsed by, or responsible for the services,
              availability, or accuracy of any third-party providers. Your use of third-party
              services is subject to their respective terms of service and privacy policies.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">Your Responsibility</h2>
            <p className="text-muted-foreground leading-relaxed">
              If you choose to deploy or modify this software for real-money trading, you do so
              entirely at your own risk. You are solely responsible for your own trading decisions
              and their outcomes. Algorithmic trading may be subject to regulations in your
              jurisdiction, and it is your responsibility to ensure compliance with all applicable
              laws and regulations.
            </p>
          </section>
        </div>

        <div className="mt-12 pt-6 border-t flex gap-4">
          <Link
            href="/terms"
            className="text-sm text-primary hover:underline"
          >
            View Terms of Use &rarr;
          </Link>
          <Link
            href="/privacy"
            className="text-sm text-primary hover:underline"
          >
            View Privacy Policy &rarr;
          </Link>
        </div>
      </div>
    </div>
  );
}
