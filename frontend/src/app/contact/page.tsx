// src/app/contact/page.tsx
import type { Metadata } from 'next';
import ContactForm from '@/components/ContactForm'; // Import the form component

export const metadata: Metadata = {
  title: 'Contact | Unfog London',
  description: 'Get in touch with Unfog London. Send a message regarding your curated London events newsletter.',
};

export default function ContactPage() {
  return (
    <div className="bg-white dark:bg-neutral-900 text-neutral-800 dark:text-neutral-200 py-12 sm:py-16">
      <div className="max-w-xl mx-auto px-6">
        <header className="mb-10 sm:mb-12 text-center">
          <h1 className="text-4xl sm:text-5xl font-serif font-semibold text-neutral-900 dark:text-neutral-100">
            Get in Touch
          </h1>
          <p className="mt-3 text-lg text-neutral-600 dark:text-neutral-400">
            Have a question, suggestion, or just want to say hi? Drop me a line!
          </p>
        </header>

        <ContactForm />
      </div>
    </div>
  );
}