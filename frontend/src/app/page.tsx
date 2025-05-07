"use client" // Keep if SignupForm needs it

// Keep your existing imports
import SignupForm from '@/components/SignupForm'
import Image from 'next/image'; // Import Next.js Image

export default function Home() {

  return (
    // Kept backgrounds to override body background if needed
    <main className="bg-[#F5F2EE] text-black dark:bg-[#0A0A0A] dark:text-white w-full">

      {/* This section no longer needs flex-grow, its parent div handles it */}
      <section className="flex flex-col items-center justify-center px-6 py-16 sm:py-24 text-center space-y-12 min-h-screen"> {/* Added min-h-screen back to ensure content centers vertically */}
        {/* Wide headline */}
        <h1 className="text-5xl sm:text-6xl font-serif font-semibold leading-tight tracking-tight max-w-5xl mx-auto">
          Local London events, tailored to&nbsp;
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
          The weekly events newsletter tuned to your interests and locale. Only from hand-picked venues. And yes, it's free.
        </p>

        {/* Signup card - Unchanged */}
        <SignupForm />

        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Join fellow <span className="font-medium">Londoners</span> enjoying better weekends.
        </p>
      </section>

      {/* --- ADD CORNER IMAGES HERE --- */}
      {/* These images will be fixed to the viewport corners */}
      {/* They are hidden by default, and appear on 'md' screens and up */}

      {/* Bottom-left image */}
      <div className="hidden md:block fixed bottom-0 left-0 m-4 lg:m-8 z-0 pointer-events-none">
        <Image
          src="/london-events-2.png"
          alt="" // Decorative
          width={160}
          height={100}
          className="w-64 h-auto lg:w-64 dark"
        />
      </div>

      {/* Bottom-right image */}
      <div className="hidden md:block fixed bottom-0 right-0 m-4 lg:m-8 z-0 pointer-events-none">
        <Image
          src="/london-events-3.png"
          alt=""
          width={160}
          height={100}
          className="w-64 h-auto lg:w-64 dark"
        />
      </div>
      {/* --- END CORNER IMAGES --- */}

    </main>
  )
}