import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Privacy Policy | Bringetto Trading Agent',
  description: 'Privacy Policy for Bringetto Trading Agent',
};

export default function PrivacyPage() {
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

        <h1 className="text-3xl font-bold mb-2">Privacy Policy</h1>
        <p className="text-muted-foreground mb-8">Last updated: February 2026</p>

        <div className="prose prose-neutral dark:prose-invert max-w-none space-y-6">
          <section>
            <h2 className="text-xl font-semibold mb-3">1. Introduction</h2>
            <p className="text-muted-foreground leading-relaxed">
              This Privacy Policy describes how the Bringetto Trading Agent application
              (&quot;the Application&quot;) collects, uses, and protects information. This Application
              is designed for personal use and paper trading purposes only.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">2. Information We Collect</h2>
            <p className="text-muted-foreground leading-relaxed mb-3">
              The Application may collect and store the following types of information:
            </p>
            <ul className="list-disc list-inside text-muted-foreground space-y-2 ml-4">
              <li>
                <strong>Trading Data:</strong> Paper trading orders, positions, and transaction
                history from your Alpaca paper trading account
              </li>
              <li>
                <strong>Market Data:</strong> Stock quotes, historical prices, and market
                information retrieved from Alpaca&apos;s data APIs
              </li>
              <li>
                <strong>Strategy Performance:</strong> Analytics and metrics related to trading
                strategy performance, win rates, and profit/loss calculations
              </li>
              <li>
                <strong>System Logs:</strong> Technical logs for debugging and monitoring
                application performance
              </li>
              <li>
                <strong>Authentication Data:</strong> Basic session information for dashboard access
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">3. How We Use Information</h2>
            <p className="text-muted-foreground leading-relaxed mb-3">
              Information collected by the Application is used for:
            </p>
            <ul className="list-disc list-inside text-muted-foreground space-y-2 ml-4">
              <li>Executing and tracking paper trading orders</li>
              <li>Analyzing trading strategy performance</li>
              <li>Generating performance reports and analytics</li>
              <li>Monitoring system health and debugging issues</li>
              <li>Improving trading algorithms and strategies</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">4. Data Storage</h2>
            <p className="text-muted-foreground leading-relaxed">
              Trading data and analytics are stored in a PostgreSQL database. The Application
              is deployed on Railway (backend) and Vercel (dashboard). Data is retained for
              the purpose of analyzing trading performance over time. You may request deletion
              of your data by contacting the application administrator.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">5. Third-Party Services</h2>
            <p className="text-muted-foreground leading-relaxed mb-3">
              The Application integrates with the following third-party services:
            </p>
            <ul className="list-disc list-inside text-muted-foreground space-y-2 ml-4">
              <li>
                <strong>Alpaca Markets:</strong> Brokerage and market data services. Your use
                of Alpaca is subject to{' '}
                <a
                  href="https://alpaca.markets/disclosures"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  Alpaca&apos;s privacy policy and disclosures
                </a>
              </li>
              <li>
                <strong>Railway:</strong> Backend hosting platform
              </li>
              <li>
                <strong>Vercel:</strong> Dashboard hosting platform
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">6. Data Security</h2>
            <p className="text-muted-foreground leading-relaxed">
              We implement reasonable security measures to protect the information stored by
              the Application. API keys and sensitive credentials are stored as environment
              variables and are never exposed in client-side code. However, no method of
              electronic storage is 100% secure, and we cannot guarantee absolute security.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">7. Data Sharing</h2>
            <p className="text-muted-foreground leading-relaxed">
              This is a personal-use application. We do not sell, trade, or otherwise transfer
              your information to third parties. Information may be shared with third-party
              service providers (Alpaca, Railway, Vercel) only as necessary to operate the
              Application.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">8. Cookies and Tracking</h2>
            <p className="text-muted-foreground leading-relaxed">
              The Application uses a session cookie for authentication purposes only. We do
              not use tracking cookies, analytics services, or advertising technologies.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">9. Your Rights</h2>
            <p className="text-muted-foreground leading-relaxed">
              As this is a personal-use application, you have full control over your data.
              You may request access to, correction of, or deletion of your data at any time
              by contacting the application administrator.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">10. Changes to This Policy</h2>
            <p className="text-muted-foreground leading-relaxed">
              We may update this Privacy Policy from time to time. Changes will be reflected
              on this page with an updated revision date. Your continued use of the Application
              after any changes constitutes acceptance of the updated policy.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">11. Contact</h2>
            <p className="text-muted-foreground leading-relaxed">
              If you have any questions about this Privacy Policy or how your data is handled,
              please contact the application administrator.
            </p>
          </section>
        </div>

        <div className="mt-12 pt-6 border-t">
          <Link
            href="/terms"
            className="text-sm text-primary hover:underline"
          >
            View Terms of Use &rarr;
          </Link>
        </div>
      </div>
    </div>
  );
}
