// src/components/SignupForm.tsx
'use client'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import dynamic from 'next/dynamic'
import {
  subscriptionSchema,
  type SubscriptionFormInput, // Type for react-hook-form state
  type SubscriptionFormData,  // Type for the API payload
  interestTags as fallbackTags,
} from '@/lib/validation' // Assuming these types are defined in your validation file

const Turnstile = dynamic(
  () => import('@marsidev/react-turnstile').then(m => m.Turnstile),
  { ssr: false }
)

/* coloured confetti (unchanged) */
const confettiColors = [
  'bg-pink-500','bg-yellow-500','bg-green-500',
  'bg-blue-500','bg-indigo-500','bg-purple-500','bg-red-500',
]

/* ───── colour map ─────
   keep all strings literal so Tailwind sees them */
const colourMap: Record<string, {
  btnBg: string
  btnHover: string
  ring: string
  focusRingColor: string // General focus ring for inputs (can be different from darkRing)
  darkFocusRingColor: string // Specific focus ring for inputs in dark mode
  border: string
  // peerChecked is complex because it involves peer state, handle directly in JSX or simplify
  selectedPill: string
}> = {
  emerald: {
    btnBg       : 'bg-emerald-500',
    btnHover    : 'hover:bg-emerald-600',
    ring        : 'focus:ring-emerald-500', // For main CTA button
    focusRingColor: 'focus:ring-emerald-500/40', // For inputs in light mode
    darkFocusRingColor: 'focus:ring-emerald-500/30', // For inputs in dark mode
    border      : 'border-emerald-500',
    selectedPill: 'bg-emerald-500 text-white border-emerald-500',
  },
  red: {
    btnBg       : 'bg-red-500',
    btnHover    : 'hover:bg-red-600',
    ring        : 'focus:ring-red-500',
    focusRingColor: 'focus:ring-red-500/40',
    darkFocusRingColor: 'focus:ring-red-500/30',
    border      : 'border-red-500',
    selectedPill: 'bg-red-500 text-white border-red-500',
  },
  blue: {
    btnBg       : 'bg-blue-500',
    btnHover    : 'hover:bg-blue-600',
    ring        : 'focus:ring-blue-500',
    focusRingColor: 'focus:ring-blue-500/40',
    darkFocusRingColor: 'focus:ring-blue-500/30',
    border      : 'border-blue-500',
    selectedPill: 'bg-blue-500 text-white border-blue-500',
  },
  purple: {
    btnBg       : 'bg-purple-500',
    btnHover    : 'hover:bg-purple-600',
    ring        : 'focus:ring-purple-500',
    focusRingColor: 'focus:ring-purple-500/40',
    darkFocusRingColor: 'focus:ring-purple-500/30',
    border      : 'border-purple-500',
    selectedPill: 'bg-purple-500 text-white border-purple-500',
  },
  indigo: {
    btnBg       : 'bg-indigo-500',
    btnHover    : 'hover:bg-indigo-600',
    ring        : 'focus:ring-indigo-500',
    focusRingColor: 'focus:ring-indigo-500/40',
    darkFocusRingColor: 'focus:ring-indigo-500/30',
    border      : 'border-indigo-500',
    selectedPill: 'bg-indigo-500 text-white border-indigo-500',
  },
}

// Define the Interest type based on fallbackTags
type Interest = typeof fallbackTags[number]; // "Art" | "Food & Drink" | …

/* ───── props ───── */
interface SignupFormProps {
  events?: string[]
  ctaText?: string
  /** overall look */
  mode?: 'light' | 'dark'
  /** accent colour */
  primaryColor?: keyof typeof colourMap
  newsletterSlug?: string
}

export default function SignupForm({
  events,
  ctaText       = 'Subscribe',
  mode          = 'dark', // Default mode
  primaryColor  = 'emerald', // Default primary color
  newsletterSlug = 'default', // Default newsletter slug
}: SignupFormProps) {
  /* ───── derive theme and color helpers ───── */
  // Get color configuration, defaulting to emerald if primaryColor is invalid
  const C       = colourMap[primaryColor] ?? colourMap.emerald
  const isLight = mode === 'light'

  /* ───── determine available tags for interests ───── */
  const availableTags   = (events?.length ? events : fallbackTags) as Interest[]
  const showInterestUI  = availableTags.length > 1
  const singleInterest  = availableTags.length === 1 ? availableTags[0] : null

  /* ───── state for confetti burst effect ───── */
  const [burst, setBurst] = useState<string | null>(null)

  /* ───── react-hook-form setup ───── */
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<SubscriptionFormInput>({ // Use SubscriptionFormInput for form state
    resolver: zodResolver(subscriptionSchema),
    defaultValues: {
      email     : '',
      postcode  : '',
      interests : singleInterest ? [singleInterest] : [],
      website   : '', // Honeypot field
      cfToken   : '', // Cloudflare Turnstile token
      newsletter: newsletterSlug, // Will always be a string due to prop default
    },
  })

  /* ───── toggle interest pill selection ───── */
  function toggleTag(tag: Interest) {
    const currentInterests = watch('interests') ?? []
    const current = new Set<Interest>(currentInterests)
    const adding  = !current.has(tag)

    adding ? current.add(tag) : current.delete(tag)
    // Ensure setValue is called with the correct type for interests (Interest[])
    setValue('interests', Array.from(current), { shouldValidate: true })

    if (adding) {
      setBurst(tag) // Trigger confetti
      setTimeout(() => setBurst(null), 600) // Reset confetti state
    }
  }

  /* ───── form submission handler ───── */
  // onSubmit now correctly expects data of type SubscriptionFormInput
  const onSubmit = async (data: SubscriptionFormInput) => {
    // Construct the final payload for the API, ensuring it matches SubscriptionFormData
    // data.newsletter is typed as string | undefined in SubscriptionFormInput,
    // but it's guaranteed to be a string here due to defaultValues.
    // The non-null assertion (!) is safe.
    const payloadForApi: SubscriptionFormData = {
      email: data.email,
      postcode: data.postcode,
      interests: data.interests, // data.interests is already correctly Interest[]
      cfToken: data.cfToken,
      newsletter: data.newsletter!, // Assert non-null: safe due to defaultValues
      website: data.website, // Optional field
    };

    try {
      const r = await fetch('/api/subscribe', {
        method : 'POST',
        headers: { 'Content-Type':'application/json' },
        body   : JSON.stringify(payloadForApi),
      })

      const result = await r.json().catch(() => ({})) // Catch potential JSON parsing errors

      if (r.ok) {
        // Consider using a more user-friendly notification system instead of alert
        alert('Check your inbox to confirm!')
      } else {
        console.error('Submit error:', r.status, result)
        const specificError =
          result.details?.postcode?.[0] ||
          result.details?.email?.[0] ||
          result.details?.interests?.[0] ||
          result.details?.cfToken?.[0]
        alert(`Error: ${specificError || result.error || 'An unknown error occurred.'}`)
      }
    } catch (error) {
      console.error('Network or unexpected error during submit:', error)
      alert('An unexpected error occurred. Please try again.')
    }
  }

  /* ───── set Cloudflare Turnstile token ───── */
  const setToken = (token: string | null) =>
    setValue('cfToken', token ?? '', { shouldValidate: true })

  /* ───── Dynamic CSS classes based on theme and color ───── */
  const wrapperClass = `
    shadow-md rounded-xl px-6 py-8 space-y-6 text-left max-w-xl w-full
    ${isLight ? 'bg-white text-neutral-800' : 'bg-neutral-900 text-white'}
  `

  const inputBaseClasses = `w-full p-3 rounded border focus:outline-none focus:ring-4`
  const inputThemeClasses = isLight
    ? `bg-white text-neutral-900 border-neutral-300 placeholder:text-neutral-400 ${C.focusRingColor}`
    : `bg-neutral-800 text-white border-neutral-700 placeholder:text-neutral-500 ${C.darkFocusRingColor}`

  const getInputClasses = (hasError: boolean, additionalClasses: string = '') => `
    ${inputBaseClasses} ${additionalClasses}
    ${hasError ? 'border-red-500' : inputThemeClasses}
  `

  const tooltipIconClasses = `
    w-5 h-5 transition-colors
    ${isLight
      ? 'text-neutral-400 group-hover:text-neutral-600 group-focus-visible:text-neutral-600'
      : 'text-neutral-500 group-hover:text-neutral-300 group-focus-visible:text-neutral-300'}
  `
  const tooltipTextClasses = `
    absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 w-max max-w-[200px]
    text-xs rounded py-1.5 px-3 shadow-lg z-10
    pointer-events-none opacity-0 scale-90 transition-all duration-200 ease-in-out
    group-hover:opacity-100 group-hover:scale-100 group-focus-visible:opacity-100 group-focus-visible:scale-100
    ${isLight ? 'bg-neutral-800 text-white' : 'bg-neutral-700 text-white'}
  `
  const interestsLabelTextClasses = isLight ? 'text-neutral-700' : 'text-neutral-400'

  const unselectedPillClasses = `
    inline-block px-3 py-1 border rounded-full text-sm transition duration-150 group-active:scale-95
    ${isLight
        ? 'bg-white border-neutral-300 text-neutral-700 hover:border-neutral-500'
        : 'bg-neutral-800 border-neutral-600 text-neutral-300 hover:border-neutral-400'}
  `
  // Selected pill classes use the primary color from the colourMap
  const selectedPillClasses = `
    inline-block px-3 py-1 border rounded-full text-sm transition duration-150 group-active:scale-95
    ${C.selectedPill}
  `
  const ctaButtonClasses = `
    w-full ${C.btnBg} ${C.btnHover} text-white py-3 rounded font-semibold
    transition duration-150 ease-in-out focus:outline-none focus:ring-2 ${C.ring}
    focus:ring-offset-2 ${isLight ? 'focus:ring-offset-white' : 'focus:ring-offset-neutral-900'}
  `

  /* JSX ---------------------------------------------------------------- */
  return (
    <form onSubmit={handleSubmit(onSubmit)} className={wrapperClass}>
      {/* Honeypot field for bot detection */}
      <input type="text" tabIndex={-1} className="hidden" {...register('website')} />
      {/* Hidden field for newsletter slug */}
      <input
          type="hidden"
          value={newsletterSlug}
          {...register('newsletter')}
        />

      {/* Email + Postcode group */}
      <div className="flex flex-col sm:flex-row gap-4 relative pb-7">
        {/* Email field */}
        <div className="flex-1 relative">
          <label className="sr-only" htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            {...register('email')}
            placeholder="Your email address"
            className={getInputClasses(!!errors.email)}
            aria-invalid={errors.email ? 'true' : 'false'}
          />
          {errors.email && (
            <p className="absolute left-0 top-full mt-1 text-xs text-red-500">
              {errors.email.message}
            </p>
          )}
        </div>

        {/* Postcode field */}
        <div className="relative w-full sm:w-[170px] flex-shrink-0">
          <label className="sr-only" htmlFor="postcode">Postcode</label>
          <input
            id="postcode"
            {...register('postcode')}
            placeholder="Postcode"
            className={getInputClasses(!!errors.postcode, 'pr-8')} // Added pr-8 for icon spacing
            aria-invalid={errors.postcode ? 'true' : 'false'}
          />
          {/* Tooltip icon for postcode */}
          <button
            type="button" // Important: type="button" to prevent form submission
            className="absolute inset-y-0 right-0 flex items-center pr-3 group cursor-help focus:outline-none"
            aria-label="Why we ask for your postcode"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"
              strokeWidth={1.5} stroke="currentColor"
              className={tooltipIconClasses}
              aria-hidden="true"
            >
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z"
              />
            </svg>
            <span role="tooltip" className={tooltipTextClasses}>
              We use your postcode to find relevant events happening near you.
            </span>
          </button>
          {errors.postcode && (
            <p className="absolute right-0 top-full mt-1 max-w-[170px] text-xs text-red-500 text-right">
              {errors.postcode.message}
            </p>
          )}
        </div>
      </div>

      {/* Interest pills / hidden field */}
      {showInterestUI ? (
        <div>
          <span className={`block text-sm font-medium mb-2 ${interestsLabelTextClasses}`}>
            What tickles your fancy?
          </span>
          <div className="flex flex-wrap gap-2">
            {availableTags.map(tag => {
              const isChecked = watch('interests')?.includes(tag)
              return (
                <div key={tag} className="relative">
                  <label className="cursor-pointer group">
                    <input
                      type="checkbox"
                      value={tag}
                      // No need to spread register here if using setValue directly
                      // {...register('interests')} // This can be removed if toggleTag handles all logic
                      checked={isChecked} // Control checked state
                      className="peer hidden" // Tailwind peer class for styling based on state
                      onChange={() => toggleTag(tag)}
                      aria-labelledby={`interest-label-${tag}`}
                    />
                    <span
                      id={`interest-label-${tag}`}
                      className={isChecked ? selectedPillClasses : unselectedPillClasses}
                    >
                      {tag}
                    </span>
                    {/* Confetti effect */}
                    {burst === tag && Array.from({ length: 12 }).map((_, i) => {
                      const angle = Math.random() * 360
                      const dist  = 20 + Math.random() * 15
                      const dx    = Math.cos(angle) * dist
                      const dy    = Math.sin(angle) * dist
                      const size  = 2 + Math.random() * 2
                      const confettiColor = confettiColors[Math.floor(Math.random() * confettiColors.length)]
                      return (
                        <div
                          key={i}
                          style={{
                            '--dx'   : `${dx}px`,
                            '--dy'   : `${dy}px`,
                            '--angle': `${Math.random()*360}deg`,
                            left     : '50%',
                            top      : '40%',
                            width    : `${size}px`,
                            height   : `${size * 2}px`,
                            animationDelay:`${Math.random()*0.04}s`,
                          } as React.CSSProperties}
                          className={`absolute pointer-events-none animate-[tiny-confetti-pop_0.6s_ease-out_forwards] ${confettiColor}`}
                        />
                      )
                    })}
                  </label>
                </div>
              )
            })}
          </div>
          {errors.interests && (
            <p className="text-xs text-red-500 mt-1">{errors.interests.message}</p>
          )}
        </div>
      ) : (
        // If only one interest or no interests to choose from, it's handled by defaultValues
        // and the hidden newsletter input already covers the submission.
        // The `interests` field in the form will have the singleInterest or be empty.
        // No need for an additional hidden input for interests here as RHF handles it.
        null // Or <input type="hidden" {...register('interests')} /> if explicit registration is preferred
      )}

      {/* Cloudflare Turnstile Captcha */}
      <div>
        <Turnstile
          siteKey={process.env.NEXT_PUBLIC_CF_SITE_KEY!} // Ensure this env var is set
          onSuccess={setToken}
          options={{ theme: mode }} // Pass the current mode ('light' or 'dark') or 'auto'
        />
        {errors.cfToken && (
          <p className="text-xs text-red-500 mt-1">{errors.cfToken.message}</p>
        )}
      </div>

      {/* CTA button */}
      <button type="submit" className={ctaButtonClasses}>
        {ctaText}
      </button>
    </form>
  )
}
