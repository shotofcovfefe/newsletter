'use client'

import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import dynamic from 'next/dynamic'
const Turnstile = dynamic(
  () => import('@marsidev/react-turnstile').then(m => m.Turnstile),
  { ssr: false }            // ⬅ prevent server-side import
)
import * as z from 'zod'

/* ------------ constants ------------ */
const interestTags = [
  'Art', 'Food & Drink', 'Live Music', 'Workshops',
  'Comedy', 'Markets', 'Families', 'Date Night', 'Solo Friendly'
] as const

const confettiColors = [
  'bg-pink-500','bg-yellow-500','bg-green-500',
  'bg-blue-500','bg-indigo-500','bg-purple-500','bg-red-500'
]

/* ------------ zod schema ------------ */
const ukPostcode = /^([A-Z]{1,2}\d[A-Z\d]? ?\d[ABD-HJLNP-UW-Z]{2})$/i
const schema = z.object({
  email    : z.string().email("Invalid email address"), // Added specific message
  postcode : z.string().trim().regex(ukPostcode, 'Invalid UK postcode'), // Added specific message
  interests: z.array(z.enum(interestTags)).min(1, 'Pick at least one interest'), // Added specific message
  website  : z.string().max(0).optional(),   // honeypot
  cfToken  : z.string().min(1, { message: "Captcha completion required" }), // Added specific message
})
type FormData = z.infer<typeof schema>

/* ------------ component ------------ */
export default function SignupForm() {
  const [burst, setBurst] = useState<string | null>(null)

  /* react-hook-form */
  // Added formState to access errors easily if needed later
  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm<FormData>({
  resolver: zodResolver(schema),
  defaultValues: {
    email: '',
    postcode: '',
    interests: [],
    website: '',
    cfToken: '',
  },
})



  /* tag toggle keeps styling identical */
  const toggleTag = (tag: typeof interestTags[number]) => {
    const current = new Set(watch('interests') ?? [])
    if (current.has(tag)) {
        current.delete(tag);
    } else {
        current.add(tag);
    }
    setValue('interests', Array.from(current) as any)
    // --- Adjusted burst logic slightly to trigger on add ---
    if (current.has(tag)) { // Check if tag exists *after* toggle (meaning it was added)
        setBurst(tag)
        setTimeout(()=>setBurst(null), 600)
    }
  }

  /* submit handler → call API */
  const onSubmit = async (data:FormData) => {
    // Optional: Log data being sent for debugging
    // console.log('Submitting:', data);
    const r = await fetch('/api/subscribe', {
      method :'POST',
      headers:{ 'Content-Type':'application/json' },
      body   : JSON.stringify(data),
    })
    const result = await r.json().catch(() => ({})); // Attempt to parse JSON, default to {} on failure

    if (r.ok) {
        alert('Check your inbox to confirm!');
        // Consider resetting the form here: reset();
    } else {
        console.error("Submit error:", r.status, result);
        // Provide more specific feedback if possible
        const errorMsg = result.error || 'An error occurred. Please try again.';
        alert(`Error: ${errorMsg}`);
    }
  }

  /* Turnstile token setter */
  const setToken = (token:string|null) => {
    // console.log('Turnstile Token:', token); // Optional: Log token for debugging
    setValue('cfToken', token || '', { shouldValidate: true }); // Validate cfToken when set
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="bg-white dark:bg-neutral-900 shadow-md rounded-xl px-6 py-8 space-y-6
                 text-left max-w-xl w-full"
    >
      {/* honeypot - keeps bots at bay but invisible */}
      <input type="text" tabIndex={-1} className="hidden" {...register('website')} />

      {/* Turnstile widget */}
      <Turnstile
        siteKey={process.env.NEXT_PUBLIC_CF_SITE_KEY!}
        onSuccess={setToken}
        options={{ theme: 'auto' }} // Use 'auto' theme to respect user preference
        // Consider adding error handling: onError, onExpire
      />
      {/* Display Captcha errors if any */}
      {errors.cfToken && <p className="text-xs text-red-500 mt-1">{errors.cfToken.message}</p>}


      {/* ---- Email + Postcode ---- */}
      <div className="flex flex-col sm:flex-row gap-4">
        {/* Email Field */}
        <div className="flex-1">
          <label className="sr-only" htmlFor="email">Email</label>
          <input
            id="email"
            type="email" // Use type="email" for better semantics/validation
            {...register('email')}
            placeholder="Your email address"
            className={`w-full p-3 rounded border ${errors.email ? 'border-red-500' : 'border-neutral-300 dark:border-neutral-700'}
                       dark:bg-neutral-800 dark:text-white focus:outline-none
                       focus:ring-4 focus:ring-black/20 dark:focus:ring-emerald-500/30`}
            aria-invalid={errors.email ? "true" : "false"}
          />
           {errors.email && <p className="text-xs text-red-500 mt-1">{errors.email.message}</p>}
        </div>

        {/* Postcode Field + Tooltip */}
        <div className="relative w-full sm:w-auto"> {/* Added relative wrapper */}
          <label className="sr-only" htmlFor="postcode">Postcode</label>
          <input
            id="postcode"
            {...register('postcode')}
            placeholder="Postcode"
            // Added pr-8 for icon space, adjusted width slightly if needed
            className={`p-3 w-full sm:w-[170px] rounded border ${errors.postcode ? 'border-red-500' : 'border-neutral-300 dark:border-neutral-700'}
                       dark:bg-neutral-800 dark:text-white focus:outline-none
                       focus:ring-4 focus:ring-black/20 dark:focus:ring-emerald-500/30 pr-8`}
            aria-invalid={errors.postcode ? "true" : "false"}
          />
          {/* Tooltip Trigger Area (Icon) */}
          <div className="absolute inset-y-0 right-0 flex items-center pr-3 group cursor-help">
             {/* Heroicon: question-mark-circle */}
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="w-5 h-5 text-neutral-400 group-hover:text-neutral-600 dark:group-hover:text-neutral-200 transition-colors"
              aria-hidden="true" // Hide decorative icon from screen readers
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z" />
            </svg>
            {/* Tooltip Text (Appears on hover) */}
            <span
              role="tooltip" // Add role for accessibility
              className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 w-max max-w-[200px]
                         bg-neutral-800 text-white text-xs rounded py-1.5 px-3 shadow-lg z-10 pointer-events-none
                         opacity-0 scale-90 group-hover:opacity-100 group-hover:scale-100 transition-all duration-200 ease-in-out"
            >
              We use your postcode to find relevant events happening near you.
            </span>
          </div>
           {errors.postcode && <p className="text-xs text-red-500 mt-1">{errors.postcode.message}</p>}
        </div>
      </div>

      {/* ---- Interest pills ---- */}
      <div>
        <span className="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-400">
          What tickles your fancy?
        </span>
        <div className="flex flex-wrap gap-2">
          {interestTags.map(tag => (
            <div key={tag} className="relative">
              {/* Label now wraps input and span */}
              <label className="cursor-pointer group">
                <input
                  type="checkbox"
                  value={tag}
                  {...register('interests')}
                  className="peer hidden" // Peer is still useful for sibling selectors if needed elsewhere
                  onChange={()=>toggleTag(tag)}
                  aria-labelledby={`interest-label-${tag}`} // For better accessibility
                />
                {/* Visual representation */}
                <span
                  id={`interest-label-${tag}`} // Connects aria-labelledby
                  className={`
                    inline-block px-3 py-1 border rounded-full text-sm transition duration-150 ease-in-out
                    ${watch('interests')?.includes(tag)
                      ? 'bg-emerald-500 text-white border-emerald-500' // Checked styles
                      : 'bg-white dark:bg-neutral-800 border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300' // Unchecked styles
                    }
                    group-hover:border-neutral-500 dark:group-hover:border-neutral-400 group-active:scale-95
                  `}
                >
                  {tag}
                </span>

                 {/* confetti spark */}
                {burst === tag && Array.from({ length: 12 }).map((_, i) => {
                    // ... (confetti code unchanged) ...
                    const angle = Math.random()*360; const dist = 20+Math.random()*15; const dx = Math.cos(angle)*dist; const dy = Math.sin(angle)*dist; const size = 2+Math.random()*2; const color = confettiColors[Math.floor(Math.random()*confettiColors.length)];
                    return <div key={i} style={{'--dx':`${dx}px`, '--dy':`${dy}px`, '--angle':`${Math.random()*360}deg`, left:'50%', top:'40%', width:`${size}px`,height:`${size*2}px`, animationDelay:`${Math.random()*0.04}s`} as React.CSSProperties} className={`absolute pointer-events-none animate-[tiny-confetti-pop_0.6s_ease-out_forwards] ${color}`} />;
                })}
              </label>
            </div>
          ))}
        </div>
         {errors.interests && <p className="text-xs text-red-500 mt-1">{errors.interests.message}</p>}
      </div>

      {/* CTA */}
      <button
        type="submit"
        className="w-full bg-emerald-500 hover:bg-emerald-600 text-white
                   py-3 rounded font-semibold transition duration-150 ease-in-out
                   focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 dark:focus:ring-offset-neutral-900"
      >
        Subscribe
      </button>
    </form>
  )
}