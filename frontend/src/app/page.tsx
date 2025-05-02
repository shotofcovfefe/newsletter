"use client"
import SignupForm from '@/components/SignupForm'


export default function Home() {

  return (
    <main className="bg-[#F5F2EE] text-black dark:bg-[#0A0A0A] dark:text-white
                     min-h-screen flex flex-col justify-between">

      {/* ── Hero ──────────────────────────────────────────────── */}
      <section className="flex-1 flex flex-col items-center justify-center px-6 py-32 text-center space-y-12">
        {/* Wide headline */}
        <h1 className="text-5xl sm:text-6xl font-serif font-semibold leading-tight tracking-tight max-w-5xl mx-auto">
  Niche London events, tailored to&nbsp;
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
        <p className="text-lg sm:text-xl text-neutral-400 leading-relaxed max-w-xl mx-auto">
          Curated events matched to your postcode and interests.
          No noise. No scrolling. Just better weekends.
        </p>

        {/* ── Signup card ─────────────────────────────────────── */}
        <SignupForm />

        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Join 5,000+ Londoners finding better weekends.
        </p>
      </section>

      {/* ── Footer ───────────────────────────────────────────── */}
      <footer className="w-full text-center text-xs text-neutral-500 dark:text-neutral-400 pb-6">
        Built with 🤍 in London. No tracking. No ads. Ever.
      </footer>
    </main>
  )
}
