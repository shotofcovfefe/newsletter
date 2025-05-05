"use client" // Keep if SignupForm needs it

import SignupForm from '@/components/SignupForm'

export default function Home() {

  return (
    // REMOVED: min-h-screen, flex, flex-col from <main>
    // Kept backgrounds to override body background if needed
    <main className="bg-[#F5F2EE] text-black dark:bg-[#0A0A0A] dark:text-white w-full">

      {/* This section no longer needs flex-grow, its parent div handles it */}
      <section className="flex flex-col items-center justify-center px-6 py-16 sm:py-24 text-center space-y-12">
        {/* Wide headline */}
        <h1 className="text-5xl sm:text-6xl font-serif font-semibold leading-tight tracking-tight max-w-5xl mx-auto">
          Unfog London events, tailored to&nbsp;
          <span className="relative inline-block">
            <em className="italic font-normal">you</em>
            <span
              aria-hidden
              className="absolute left-0 -bottom-1 h-[3px] w-full bg-emerald-500/80 rounded-md"
            />
          </span>
          .
        </h1>

        {/* Sub-headline */}
        <p className="text-lg sm:text-xl text-neutral-500 dark:text-neutral-400 leading-relaxed max-w-xl mx-auto">
          The only newsletter for tailored, local events. No noise. No scrolling. Always free of charge.
        </p>

        {/* Signup card */}
        <SignupForm />

        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Join <span className="font-medium">5,000+</span> Londoners finding better weekends.
        </p>
      </section>

      {/* Footer is now rendered by layout.tsx, so nothing goes here */}

    </main>
  )
}