"use client" // Needed because it uses SignupForm which is a Client Component

import SignupForm from '@/components/SignupForm' // Adjust import path if needed
import Image from 'next/image';

export default function ArtPage() {

  return (
    // Set light background and dark text, remove dark mode variants
    <main className="bg-white text-neutral-800 w-full"> {/* Changed to white bg, darker text */}

      <section className="flex flex-col items-center justify-center px-6 py-16 sm:py-24 text-center space-y-12 min-h-screen">
        {/* Headline - text color inherited from main */}
        <h1 className="text-5xl sm:text-6xl font-serif font-semibold leading-tight tracking-tight max-w-5xl mx-auto">
          London's Art Scene, Curated for&nbsp;
          <span className="relative inline-block">
            <em className="italic font-normal">You</em>
            {/* Keep accent color, ensure it works on light bg */}
            <span
              aria-hidden
              className="absolute left-0 -bottom-1 h-[3px] w-full bg-blue-500/80 rounded-md"
            />
          </span>
          .
        </h1>

        {/* Sub-headline - remove dark:text variant */}
        <p className="text-lg sm:text-xl text-neutral-500 leading-relaxed max-w-xl mx-auto">
          Your weekly guide to the most exciting exhibitions, openings, and art events near you. Free forever.
        </p>

        {/* Use SignupForm with specific props */}
        {/* Ensure SignupForm itself renders correctly on light mode */}
        {/* If SignupForm has internal dark: classes, they might need removing too */}
        {/* Or pass appropriate light-mode classes via formClassName */}
        <SignupForm
          events       ={['Art']}          // one event → pills hidden
          mode         ="light"            // light surface / dark text
          primaryColor ="red"              // use red-500 / red-600 accents
          ctaText      ="Subscribe to Art Updates"
          newsletterSlug="art"
        />

        {/* Social proof text - remove dark:text variant */}
        <p className="text-sm text-neutral-500">
          Join fellow <span className="font-medium text-neutral-700">art lovers</span> enjoying London's culture.
        </p>
      </section>

      {/* Corner images - remove opacity classes */}
      <div className="hidden md:block fixed bottom-0 left-0 m-4 lg:m-8 z-0 pointer-events-none">
        <Image
          src="/london-art-2.png"
          alt=""
          width={180}
          height={120}
          className="w-48 h-auto lg:w-44"
        />
      </div>
      <div className="hidden md:block fixed bottom-0 right-0 m-4 lg:m-8 z-0 pointer-events-none">
        <Image
          src="/london-art-1.png"
          alt=""
          width={180}
          height={120}
          className="w-48 h-auto lg:w-44"
        />
      </div>
    </main>
  )
}