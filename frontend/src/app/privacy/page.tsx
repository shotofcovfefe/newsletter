// src/app/privacy/page.tsx
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Privacy Policy | Unfog London',
  description: 'Privacy Policy for Unfog London, your curated London events newsletter.',
};

export default function PrivacyPolicyPage() {
  return (
    <div className="bg-white dark:bg-neutral-900 text-neutral-800 dark:text-neutral-200 py-12 sm:py-16">
      <div className="max-w-3xl mx-auto px-6">
        <header className="mb-10 sm:mb-12 text-center">
          <h1 className="text-4xl sm:text-5xl font-serif font-semibold text-neutral-900 dark:text-neutral-100">
            Privacy Policy
          </h1>
          <p className="mt-3 text-lg text-neutral-600 dark:text-neutral-400">
            Last updated: May 7, 2025
          </p>
        </header>

        <article className="prose prose-lg dark:prose-invert max-w-none space-y-6 text-neutral-700 dark:text-neutral-300">
          <section>
            <h2 className="text-2xl font-semibold font-serif text-neutral-900 dark:text-neutral-100 !mb-3">1. Introduction</h2>
            <p>
              Welcome to Unfog London ("we", "us", "our"). We are committed to protecting your personal information and your right to privacy. If you have any questions or concerns about this privacy notice or our practices with regards to your personal information, please contact us using the information provided on this website.
            </p>
            <p>
              This privacy notice describes how we collect, use, and protect your information when you subscribe to our newsletter or otherwise use our services.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold font-serif text-neutral-900 dark:text-neutral-100 !mb-3">2. What Information Do We Collect?</h2>
            <p>
              When you subscribe to Unfog London, we collect the following personal information you voluntarily provide to us:
            </p>
            <ul>
              <li>Email address</li>
              <li>Postcode (to tailor event suggestions)</li>
              <li>Interests (event categories you select)</li>
            </ul>
            <p>
              We do not collect any sensitive personal information. All personal information that you provide must be true, complete, and accurate, and you must notify us of any changes to such information.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold font-serif text-neutral-900 dark:text-neutral-100 !mb-3">3. How Do We Use Your Information?</h2>
            <p>
              We use the personal information collected through our newsletter subscription for purposes described below:
            </p>
            <ul>
              <li><strong>To send you the Unfog London newsletter:</strong> To provide curated event information based on your postcode and interests.</li>
              <li><strong>To send administrative information:</strong> For example, details about your subscription, confirmation emails, or changes to our terms or policies.</li>
              <li><strong>To protect our services:</strong> We may use your information to help keep our website and services safe and secure (e.g., for fraud prevention and CAPTCHA verification).</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-semibold font-serif text-neutral-900 dark:text-neutral-100 !mb-3">4. Will Your Information Be Shared With Anyone?</h2>
            <p>
              We only share information with your consent, to comply with laws, to provide services, to protect your rights, or to fulfill legitimate business needs. Specifically:
            </p>
            <ul>
              <li><strong>Email Sending Provider (Resend):</strong> We use Resend (resend.com) to send emails. Your email address is shared with Resend for this purpose.</li>
              <li><strong>Database Provider (Supabase):</strong> Your subscription data (email, postcode, interests, tokens) is securely stored with Supabase (supabase.com).</li>
              <li><strong>CAPTCHA Provider (Cloudflare Turnstile):</strong> To protect against spam, we use Cloudflare Turnstile, which may process your IP address.</li>
              <li><strong>Analytics (if any):</strong> If analytics services are introduced, this policy will be updated. Unfog London currently operates with no tracking and no ads.</li>
            </ul>
            <p>We do not sell your personal information.</p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold font-serif text-neutral-900 dark:text-neutral-100 !mb-3">5. How Long Do We Keep Your Information?</h2>
            <p>
              We keep your personal information only as long as necessary for the purposes outlined in this notice, unless a longer retention period is required by law. When you unsubscribe, your data is marked accordingly, and you will no longer receive newsletters. You may request deletion of your data at any time.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold font-serif text-neutral-900 dark:text-neutral-100 !mb-3">6. What Are Your Privacy Rights?</h2>
            <p>
              Depending on your location, you may have rights regarding your personal information. These may include the right to access, correct, delete, or restrict processing of your information, and in some cases, the right to data portability or to object to processing. To exercise any of these rights, please contact us.
            </p>
            <p>
              You can unsubscribe from our email list at any time using the unsubscribe link in our emails or by contacting us directly.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold font-serif text-neutral-900 dark:text-neutral-100 !mb-3">7. Updates to This Notice</h2>
            <p>
              We may update this privacy notice from time to time. Any changes will be noted with a new "Last updated" date, and the revised version will be effective as soon as it is posted. We encourage you to review this notice periodically.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold font-serif text-neutral-900 dark:text-neutral-100 !mb-3">8. How to Contact Us</h2>
            <p>
              If you have any questions or comments about this notice, you may contact us through the contact form on our website or by email at the address provided there.
            </p>
          </section>
        </article>
      </div>
    </div>
  );
}
