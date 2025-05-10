// src/app/(marketing)/east-london/page.tsx
'use client' // This page uses the SignupForm component, which is a client component

import SignupForm from '@/components/SignupForm'
import Image from 'next/image'

// Component for the East London marketing page
export default function EastLondonPage() {
  return (
    // Added a subtle gradient background and ensured full height
    <main className="bg-gradient-to-br from-slate-50 to-sky-100 text-neutral-800 w-full min-h-screen flex flex-col">
      {/* Navigation (optional, example) */}
      {/* <nav className="w-full p-4 flex justify-between items-center">
        <span className="text-xl font-semibold text-neutral-700">Unfog.London</span>
        <a href="/about" className="text-neutral-600 hover:text-blue-600">About</a>
      </nav> */}

      {/* Main content section - centered and with padding */}
      <section className="flex flex-col items-center justify-center px-6 py-16 sm:py-24 text-center space-y-12 flex-grow relative z-10">

        {/* Headline with styled "East London's" */}
        {/* Ensure your project has a serif font configured in tailwind.config.js, e.g., 'font-lora' or 'font-merriweather' */}
        <h1 className="text-5xl sm:text-6xl md:text-7xl font-serif font-bold leading-tight tracking-tight max-w-4xl mx-auto text-neutral-900">
          Discover&nbsp;
          <span className="text-orange-500">East</span>
          {/* Darker neutral for "London's" for better contrast and sophistication */}
          <span className="text-neutral-800"> London&apos;s</span>
          &nbsp;Vibrant Scene, All in&nbsp;One&nbsp;
          <span className="relative inline-block">
            Place
            {/* Underline effect using the primary color (blue) */}
            <span
              aria-hidden
              className="absolute left-0 -bottom-2 sm:-bottom-3 h-[4px] sm:h-[5px] w-full bg-blue-500 rounded-md"
            />
          </span>.
        </h1>

        {/* Sub-headline */}
        <p className="text-lg sm:text-xl text-neutral-600 leading-relaxed max-w-2xl mx-auto">
          Get weekly updates on the coolest pop-ups, markets, gigs, and local happenings in East London. Curated, just for you.
        </p>

        {/* Signup form component integration */}
        {/* Added a subtle background and shadow to the form container for better separation */}
        <div className="w-full max-w-xl bg-white/80 backdrop-blur-sm p-6 sm:p-8 rounded-xl shadow-xl mt-8">
          <SignupForm
            events={['East London']}      // Pre-selects "East London" interest
            mode="light"                 // Sets the form to light mode
            primaryColor="blue"          // Sets the primary accent color to blue for the form
            ctaText="Subscribe to East London Updates" // Custom Call-To-Action text
            newsletterSlug="east-london"   // Associates submissions with the "east-london" newsletter
          />
        </div>

        {/* Social proof text */}
        <p className="text-base text-neutral-500 pt-4">
          Join thousands of <span className="font-semibold text-neutral-700">East Londoners</span> in the know.
        </p>
      </section>

      {/* Decorative corner images - hidden on small screens */}
      {/* These images are positioned fixed and behind the main content (z-0) */}
      <div className="hidden md:block fixed bottom-0 left-0 m-4 lg:m-8 z-0 pointer-events-none opacity-70">
        <Image
          src="/east-london-2.png" // Placeholder - replace with an actual East London image
          alt="Decorative silhouette of East London skyline" // Updated alt text
          width={200} // Slightly increased size
          height={130}
          className="w-52 h-auto lg:w-60" // Responsive sizing
          priority={false}
          // More descriptive placeholder text
          onError={(e) => { (e.target as HTMLImageElement).src = 'https://placehold.co/200x130/a5f3fc/0c4a6e?text=East+LDN+Skyline'; }}
        />
      </div>
      <div className="hidden md:block fixed bottom-0 right-0 m-4 lg:m-8 z-0 pointer-events-none opacity-70">
        <Image
          src="/east-london-1.png" // Placeholder - replace with an actual East London image
          alt="Decorative image of vibrant East London street art" // Updated alt text
          width={200} // Slightly increased size
          height={130}
          className="w-52 h-auto lg:w-60" // Responsive sizing
          priority={false}
          // More descriptive placeholder text
          onError={(e) => { (e.target as HTMLImageElement).src = 'https://placehold.co/200x130/f9a8d4/831843?text=East+LDN+Vibes'; }}
        />
      </div>

      {/* Footer (optional, example) */}
      {/* <footer className="w-full text-center p-6 text-sm text-neutral-500">
        &copy; {new Date().getFullYear()} Unfog.London. All rights reserved.
      </footer> */}
    </main>
  )
}
