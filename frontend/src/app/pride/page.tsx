// src/app/(marketing)/lgbtq/page.tsx
'use client' // This page uses the SignupForm component, which is a client component

import SignupForm from '@/components/SignupForm'
import Image from 'next/image'

// Define rainbow colors for the "LGBTQ+" text
// These are Tailwind CSS text color classes
const rainbowColors = [
  'text-red-500',
  'text-orange-500',
  'text-yellow-500',
  'text-green-500',
  'text-blue-500',
  'text-purple-500', // For the '+' symbol, or adjust as needed
]

export default function LGBTQPage() {
  const lgbtqText = "LGBTQ+".split(''); // Split the string into an array of characters

  return (
    <main className="bg-white text-neutral-800 w-full">
      {/* Main content section */}
      <section className="flex flex-col items-center justify-center px-6 py-16 sm:py-24 text-center space-y-12 min-h-screen relative z-10">

        {/* Headline */}
        <h1 className="text-5xl sm:text-6xl font-serif font-semibold leading-tight tracking-tight max-w-5xl mx-auto">
          London’s&nbsp; {/* Non-breaking space for better line breaks */}
          {/* Iterate over each character of "LGBTQ+" to apply rainbow colors */}
          {lgbtqText.map((char, index) => (
            <span key={index} className={rainbowColors[index % rainbowColors.length]}>
              {char}
            </span>
          ))}
          &nbsp;Scene, Curated for&nbsp;
          <span className="relative inline-block">
            <em className="italic font-normal">You</em>
            {/* Underline effect for "You" */}
            <span
              aria-hidden // Decorative element
              className="absolute left-0 -bottom-1 h-[3px] w-full bg-purple-500/80 rounded-md"
            />
          </span>
          .
        </h1>

        {/* Sub-headline */}
        <p className="text-lg sm:text-xl text-neutral-500 dark:text-neutral-400 leading-relaxed max-w-xl mx-auto">
          Weekly picks of the best queer parties, talks, art, and community events. Always free.
        </p>

        {/* Signup form component integration */}
        <div className="w-full max-w-xl"> {/* Added a container for better responsiveness of the form */}
          <SignupForm
            events={['LGBTQ+']}          // Pre-selects the "LGBTQ+" interest, pills UI will be hidden
            mode="light"                 // Sets the form to light mode (white surface / dark text)
            primaryColor="purple"        // Sets the primary accent color to purple
            ctaText="Subscribe to LGBTQ+ Updates" // Custom Call-To-Action text
            newsletterSlug="lgbtq"       // Associates submissions with the "lgbtq" newsletter
          />
        </div>


        {/* Social proof text */}
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Join fellow <span className="font-medium text-neutral-700 dark:text-neutral-200">queer Londoners</span> in the know.
        </p>
      </section>

      {/* Decorative corner images - hidden on small screens */}
      {/* These images are positioned fixed and behind the main content (z-0) */}
      <div className="hidden md:block fixed bottom-0 left-0 m-4 lg:m-8 z-0 pointer-events-none">
        <Image
          src="/london-pride-1.png" // Path to your image in the /public folder
          alt="" // Decorative image, so alt text is empty
          width={180} // Intrinsic width of the image
          height={120} // Intrinsic height of the image
          className="w-48 h-auto lg:w-44" // Responsive sizing
          priority={false} // Not critical for initial page load
        />
      </div>
      <div className="hidden md:block fixed bottom-0 right-0 m-4 lg:m-8 z-0 pointer-events-none">
        <Image
          src="/london-pride-2.png" // Path to your image in the /public folder
          alt="" // Decorative image
          width={180} // Intrinsic width of the image
          height={120} // Intrinsic height of the image
          className="w-48 h-auto lg:w-44" // Responsive sizing
          priority={false} // Not critical for initial page load
        />
      </div>
    </main>
  )
}
