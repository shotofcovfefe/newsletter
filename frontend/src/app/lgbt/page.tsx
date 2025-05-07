// src/app/(marketing)/lgbtq/page.tsx
'use client'                                                       // uses SignupForm

import SignupForm from '@/components/SignupForm'
import Image from 'next/image'

export default function LGBTQPage() {
  return (
    <main className="bg-white text-neutral-800 w-full">
      <section className="flex flex-col items-center justify-center px-6 py-16 sm:py-24 text-center space-y-12 min-h-screen">

        {/* headline */}
        <h1 className="text-5xl sm:text-6xl font-serif font-semibold leading-tight tracking-tight max-w-5xl mx-auto">
          London’s LGBTQ+ Scene, Curated for&nbsp;
          <span className="relative inline-block">
            <em className="italic font-normal">You</em>
            <span
              aria-hidden
              className="absolute left-0 -bottom-1 h-[3px] w-full bg-purple-500/80 rounded-md"
            />
          </span>
          .
        </h1>

        {/* sub-headline */}
        <p className="text-lg sm:text-xl text-neutral-500 leading-relaxed max-w-xl mx-auto">
          Weekly picks of the best queer parties, talks, art, and community events. Always free.
        </p>

        {/* signup card */}
        <SignupForm
          events={['LGBTQ+']}          // one tag → pills hidden
          mode="light"                 // white surface / dark text
          primaryColor="purple"        // purple accent everywhere
          ctaText="Subscribe to LGBTQ+ Updates"
          newsletterSlug="lgbtq"       // goes to the right confirmation template
        />

        {/* social proof */}
        <p className="text-sm text-neutral-500">
          Join fellow <span className="font-medium text-neutral-700">queer Londoners</span> in the know.
        </p>
      </section>

      {/* decorative corner images */}
      <div className="hidden md:block fixed bottom-0 left-0 m-4 lg:m-8 z-0 pointer-events-none">
        <Image
          src="/london-pride-1.png"             // swap for an LGBTQ image
          alt=""
          width={180}
          height={120}
          className="w-48 h-auto lg:w-44"
        />
      </div>
      <div className="hidden md:block fixed bottom-0 right-0 m-4 lg:m-8 z-0 pointer-events-none">
        <Image
          src="/london-pride-2.png"
          alt=""
          width={180}
          height={120}
          className="w-48 h-auto lg:w-44"
        />
      </div>
    </main>
  )
}
