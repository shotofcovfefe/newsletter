import Link from 'next/link';

export default function Footer() {
  return (
    <footer className="w-full px-4 sm:px-6 py-6 text-center border-t border-neutral-200 dark:border-neutral-800">
      <div className="space-y-2 max-w-prose mx-auto">

        {/* Slogan - More prominent */}
        <p className="text-sm text-neutral-700 dark:text-neutral-300">
          Built with 🤍 in London. No tracking. No ads. Ever.
        </p>

        {/* Copyright & Links - More subtle */}
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          &copy; {new Date().getFullYear()} Unfog London
          <span className="mx-1.5">·</span>
          <Link href="/privacy" className="underline hover:text-neutral-800 dark:hover:text-neutral-200 transition-colors duration-150">
            Privacy
          </Link>
          <span className="mx-1.5">·</span>
          <Link href="/contact" className="underline hover:text-neutral-800 dark:hover:text-neutral-200 transition-colors duration-150">
            Contact
          </Link>
          <span className="mx-1.5">·</span>
          <Link href="/newsletters" className="underline hover:text-neutral-800 dark:hover:text-neutral-200 transition-colors duration-150">
            Newsletters
          </Link>
        </p>
      </div>
    </footer>
  );
}
