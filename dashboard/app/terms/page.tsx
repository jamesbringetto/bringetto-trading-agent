import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Terms of Use | Bringetto Trading Agent',
  description: 'Terms of Use for Bringetto Trading Agent',
};

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-3xl mx-auto py-12 px-6">
        <div className="mb-8">
          <Link
            href="/login"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            &larr; Back to Login
          </Link>
        </div>

        <h1 className="text-3xl font-bold mb-2">Terms of Use</h1>
        <p className="text-muted-foreground mb-8">Last updated: February 2026</p>

        <div className="prose prose-neutral dark:prose-invert max-w-none space-y-6">
          <section>
            <h2 className="text-xl font-semibold mb-3">1. Acceptance of Terms</h2>
            <p className="text-muted-foreground leading-relaxed">
              By accessing and using the Bringetto Trading Agent application (&quot;the Application&quot;),
              you accept and agree to be bound by these Terms of Use. If you do not agree to these
              terms, please do not use the Application.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">2. Description of Service</h2>
            <p className="text-muted-foreground leading-relaxed">
              The Bringetto Trading Agent is a personal algorithmic trading application designed
              for educational and experimental purposes. The Application interfaces with Alpaca
              Markets for paper trading (simulated trading with virtual money) to test trading
              strategies and concepts.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">3. Paper Trading Only</h2>
            <p className="text-muted-foreground leading-relaxed">
              This Application is configured exclusively for paper trading through Alpaca&apos;s
              paper trading environment. Paper trading uses simulated money and does not involve
              real financial transactions. No real money is at risk when using this Application
              in its intended configuration.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">4. No Financial Advice</h2>
            <p className="text-muted-foreground leading-relaxed mb-3">
              <strong>The creator of this Application is not a financial advisor, broker, dealer,
              or licensed investment professional.</strong> The creator has no formal qualifications
              in finance, investment management, or securities trading. This Application was built
              as a personal educational and experimental project.
            </p>
            <p className="text-muted-foreground leading-relaxed">
              The Application does not provide financial, investment, tax, or legal advice.
              Any trading strategies, signals, analysis, or performance data provided by the
              Application are for educational and experimental purposes only and should not be
              relied upon for making investment decisions. You should consult with qualified
              financial, legal, and tax professionals before making any investment decisions.
              Past performance, whether from paper trading or backtesting, does not guarantee
              future results.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">5. No Warranties</h2>
            <p className="text-muted-foreground leading-relaxed">
              The Application is provided &quot;as is&quot; and &quot;as available&quot; without any warranties
              of any kind, either express or implied. We do not guarantee that the Application
              will be error-free, uninterrupted, or free of harmful components. Past performance
              of any trading strategy does not guarantee future results.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">6. Limitation of Liability</h2>
            <p className="text-muted-foreground leading-relaxed">
              To the fullest extent permitted by law, we shall not be liable for any direct,
              indirect, incidental, special, consequential, or punitive damages arising from
              your use of the Application. This includes, but is not limited to, any losses
              from trading decisions made based on information provided by the Application.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">7. Third-Party Services</h2>
            <p className="text-muted-foreground leading-relaxed">
              The Application integrates with third-party services, including Alpaca Markets
              for brokerage services and market data. Your use of these third-party services
              is subject to their respective terms of service and privacy policies. We are
              not responsible for the availability, accuracy, or reliability of third-party
              services.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">8. User Responsibilities</h2>
            <p className="text-muted-foreground leading-relaxed">
              You are responsible for maintaining the confidentiality of your account credentials
              and API keys. You agree not to use the Application for any unlawful purpose or
              in any way that could damage, disable, or impair the Application or interfere
              with any other party&apos;s use of the Application.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">9. Modifications</h2>
            <p className="text-muted-foreground leading-relaxed">
              We reserve the right to modify these Terms of Use at any time. Changes will be
              effective immediately upon posting. Your continued use of the Application after
              any changes constitutes acceptance of the new terms.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">10. Contact</h2>
            <p className="text-muted-foreground leading-relaxed">
              If you have any questions about these Terms of Use, please contact the
              application administrator.
            </p>
          </section>
        </div>

        <div className="mt-12 pt-6 border-t flex gap-4">
          <Link
            href="/disclaimer"
            className="text-sm text-primary hover:underline"
          >
            View Disclaimer &rarr;
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
