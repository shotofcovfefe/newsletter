// src/components/SignupForm.tsx
'use client'
import { useState, useEffect, useRef } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import dynamic from 'next/dynamic'
import {
  subscriptionSchema,
  type SubscriptionFormInput,
  type SubscriptionFormData,
  interestTags as fallbackTags,
} from '@/lib/validation'

// Dynamically import Turnstile to avoid SSR issues
import type { TurnstileInstance, TurnstileProps } from '@marsidev/react-turnstile';

const Turnstile = dynamic(
  () => import('@marsidev/react-turnstile').then(m => m.Turnstile),
  { ssr: false }
);

/* Coloured confetti (unchanged) */
const confettiColors = [
  'bg-pink-500','bg-yellow-500','bg-green-500',
  'bg-blue-500','bg-indigo-500','bg-purple-500','bg-red-500',
]

/* ───── Colour Map ───── */
const colourMap: Record<string, {
  btnBg: string
  btnHover: string
  ring: string
  focusRingColor: string
  darkFocusRingColor: string
  border: string
  selectedPill: string
  textSuccess: string
  bgSuccess: string
  borderSuccess: string
  iconSuccess: string
  textError: string
  bgError: string
  borderError: string
  iconError: string
}> = {
  emerald: {
    btnBg       : 'bg-emerald-500',
    btnHover    : 'hover:bg-emerald-600',
    ring        : 'focus:ring-emerald-500',
    focusRingColor: 'focus:ring-emerald-500/40',
    darkFocusRingColor: 'focus:ring-emerald-500/30',
    border      : 'border-emerald-500',
    selectedPill: 'bg-emerald-500 text-white border-emerald-500',
    textSuccess : 'text-emerald-700 dark:text-emerald-200',
    bgSuccess   : 'bg-emerald-100 dark:bg-emerald-900',
    borderSuccess: 'border-emerald-500 dark:border-emerald-700',
    iconSuccess : 'text-emerald-500 dark:text-emerald-400',
    textError   : 'text-red-700 dark:text-red-300',
    bgError     : 'bg-red-100 dark:bg-red-900',
    borderError : 'border-red-500 dark:border-red-700',
    iconError   : 'text-red-500 dark:text-red-400',
  },
  red: {
    btnBg       : 'bg-red-500',
    btnHover    : 'hover:bg-red-600',
    ring        : 'focus:ring-red-500',
    focusRingColor: 'focus:ring-red-500/40',
    darkFocusRingColor: 'focus:ring-red-500/30',
    border      : 'border-red-500',
    selectedPill: 'bg-red-500 text-white border-red-500',
    textSuccess : 'text-green-700 dark:text-green-200',
    bgSuccess   : 'bg-green-100 dark:bg-green-900',
    borderSuccess: 'border-green-500 dark:border-green-700',
    iconSuccess : 'text-green-500 dark:text-green-400',
    textError   : 'text-red-700 dark:text-red-300',
    bgError     : 'bg-red-100 dark:bg-red-900',
    borderError : 'border-red-500 dark:border-red-700',
    iconError   : 'text-red-500 dark:text-red-400',
  },
  blue: {
    btnBg       : 'bg-blue-500',
    btnHover    : 'hover:bg-blue-600',
    ring        : 'focus:ring-blue-500',
    focusRingColor: 'focus:ring-blue-500/40',
    darkFocusRingColor: 'focus:ring-blue-500/30',
    border      : 'border-blue-500',
    selectedPill: 'bg-blue-500 text-white border-blue-500',
    textSuccess : 'text-green-700 dark:text-green-200',
    bgSuccess   : 'bg-green-100 dark:bg-green-900',
    borderSuccess: 'border-green-500 dark:border-green-700',
    iconSuccess : 'text-green-500 dark:text-green-400',
    textError   : 'text-red-700 dark:text-red-300',
    bgError     : 'bg-red-100 dark:bg-red-900',
    borderError : 'border-red-500 dark:border-red-700',
    iconError   : 'text-red-500 dark:text-red-400',
  },
  purple: {
    btnBg       : 'bg-purple-500',
    btnHover    : 'hover:bg-purple-600',
    ring        : 'focus:ring-purple-500',
    focusRingColor: 'focus:ring-purple-500/40',
    darkFocusRingColor: 'focus:ring-purple-500/30',
    border      : 'border-purple-500',
    selectedPill: 'bg-purple-500 text-white border-purple-500',
    textSuccess : 'text-green-700 dark:text-green-200',
    bgSuccess   : 'bg-green-100 dark:bg-green-900',
    borderSuccess: 'border-green-500 dark:border-green-700',
    iconSuccess : 'text-green-500 dark:text-green-400',
    textError   : 'text-red-700 dark:text-red-300',
    bgError     : 'bg-red-100 dark:bg-red-900',
    borderError : 'border-red-500 dark:border-red-700',
    iconError   : 'text-red-500 dark:text-red-400',
  },
  indigo: {
    btnBg       : 'bg-indigo-500',
    btnHover    : 'hover:bg-indigo-600',
    ring        : 'focus:ring-indigo-500',
    focusRingColor: 'focus:ring-indigo-500/40',
    darkFocusRingColor: 'focus:ring-indigo-500/30',
    border      : 'border-indigo-500',
    selectedPill: 'bg-indigo-500 text-white border-indigo-500',
    textSuccess : 'text-green-700 dark:text-green-200',
    bgSuccess   : 'bg-green-100 dark:bg-green-900',
    borderSuccess: 'border-green-500 dark:border-green-700',
    iconSuccess : 'text-green-500 dark:text-green-400',
    textError   : 'text-red-700 dark:text-red-300',
    bgError     : 'bg-red-100 dark:bg-red-900',
    borderError : 'border-red-500 dark:border-red-700',
    iconError   : 'text-red-500 dark:text-red-400',
  },
}

type Interest = typeof fallbackTags[number];
type FormStatus = 'idle' | 'submitting' | 'success' | 'error';

interface SignupFormProps {
  events?: string[]
  ctaText?: string
  mode?: 'light' | 'dark'
  primaryColor?: keyof typeof colourMap
  newsletterSlug?: string
}

export default function SignupForm({
  events,
  ctaText       = 'Subscribe',
  mode          = 'dark',
  primaryColor  = 'emerald',
  newsletterSlug = 'default',
}: SignupFormProps) {
  const C       = colourMap[primaryColor] ?? colourMap.emerald
  const isLight = mode === 'light'

  const availableTags   = (events?.length ? events : fallbackTags) as Interest[]
  const showInterestUI  = availableTags.length > 1
  const singleInterest  = availableTags.length === 1 ? availableTags[0] : null

  const [burst, setBurst] = useState<string | null>(null)
  const [formStatus, setFormStatus] = useState<FormStatus>('idle');
  const [formMessage, setFormMessage] = useState<string>('');

  const turnstileRef = useRef<TurnstileInstance>(null);
  const emailInputRef = useRef<HTMLInputElement | null>(null);


  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<SubscriptionFormInput>({
    resolver: zodResolver(subscriptionSchema),
    defaultValues: {
      email     : '',
      postcode  : '',
      interests : singleInterest ? [singleInterest] : [],
      website   : '',
      cfToken   : '',
      newsletter: newsletterSlug,
    },
  })

  const { ref: emailFieldRefFromRHF, ...emailFieldRestPropsFromRHF } = register('email');

  // Determine if there are errors in the input group to adjust padding
  const hasInputGroupErrors = !!(errors.email || errors.postcode);

  useEffect(() => {
    if (formStatus === 'success' || formStatus === 'error') {
      const timer = setTimeout(() => {
        setFormStatus('idle');
        setFormMessage('');
      }, 7000);
      return () => clearTimeout(timer);
    }
  }, [formStatus]);

  const handleInteraction = () => {
    if (formStatus !== 'submitting') {
      setFormStatus('idle');
      setFormMessage('');
    }
  };

  function toggleTag(tag: Interest) {
    if (formStatus === 'submitting') return;
    handleInteraction();

    const currentInterests = watch('interests') ?? []
    const current = new Set<Interest>(currentInterests)
    const adding  = !current.has(tag)

    adding ? current.add(tag) : current.delete(tag)
    setValue('interests', Array.from(current), { shouldValidate: true })

    if (adding) {
      setBurst(tag)
      setTimeout(() => setBurst(null), 600)
    }
  }

  const onSubmit = async (data: SubscriptionFormInput) => {
    setFormStatus('submitting');
    setFormMessage('');

    const payloadForApi: SubscriptionFormData = {
      email: data.email,
      postcode: data.postcode,
      interests: data.interests,
      cfToken: data.cfToken,
      newsletter: data.newsletter!,
      website: data.website,
    };

    try {
      const r = await fetch('/api/subscribe', {
        method : 'POST',
        headers: { 'Content-Type':'application/json' },
        body   : JSON.stringify(payloadForApi),
      })
      const result = await r.json().catch(() => ({}));

      if (r.ok) {
        setFormStatus('success');
        setFormMessage('Success! Check your inbox to confirm your subscription.');
        reset();
        turnstileRef.current?.reset();
        setValue('cfToken', '', { shouldValidate: false });
        emailInputRef.current?.focus();
      } else {
        console.error('Submit error:', r.status, result);
        const specificError =
          result.details?.postcode?.[0] ||
          result.details?.email?.[0] ||
          result.details?.interests?.[0] ||
          result.details?.cfToken?.[0];
        setFormStatus('error');
        setFormMessage(specificError || result.error || 'An unknown error occurred. Please try again.');
      }
    } catch (error) {
      console.error('Network or unexpected error during submit:', error);
      setFormStatus('error');
      setFormMessage('An unexpected network error occurred. Please try again.');
    }
  }

  const setToken = (token: string | null) => {
    setValue('cfToken', token ?? '', { shouldValidate: true });
    if (token) {
        if (formStatus === 'error' && formMessage.toLowerCase().includes('captcha')) {
            handleInteraction();
        }
    }
  }

  const modeBaseTextClass = isLight ? 'text-neutral-800' : 'text-white';
  const wrapperClass = `
    shadow-md rounded-xl px-6 py-8 space-y-4 text-left max-w-xl w-full
    ${isLight ? 'bg-white' : 'bg-neutral-900'} ${modeBaseTextClass}
  `

  const inputBaseClasses = `w-full p-3 rounded border focus:outline-none focus:ring-4 disabled:opacity-70 disabled:cursor-not-allowed transition-colors duration-150`
  const inputThemeClasses = isLight
    ? `bg-white text-neutral-900 border-neutral-300 placeholder:text-neutral-400 ${C.focusRingColor}`
    : `bg-neutral-800 text-white border-neutral-700 placeholder:text-neutral-500 ${C.darkFocusRingColor}`

  const getInputClasses = (hasError: boolean, additionalClasses: string = '') => `
    ${inputBaseClasses} ${additionalClasses}
    ${hasError ? (isLight ? 'border-red-500' : 'border-red-400') : inputThemeClasses}
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
    inline-flex items-center px-3 py-1 border rounded-full text-sm transition-all duration-150 group-active:scale-95 cursor-pointer
    ${isLight
        ? 'bg-white border-neutral-300 text-neutral-700 hover:border-neutral-500 hover:bg-neutral-50'
        : 'bg-neutral-800 border-neutral-600 text-neutral-300 hover:border-neutral-400 hover:bg-neutral-700'}
  `
  const selectedPillClasses = `
    inline-flex items-center px-3 py-1 border rounded-full text-sm transition-all duration-150 group-active:scale-95 cursor-pointer
    ${C.selectedPill}
  `
  const ctaButtonClasses = `
    w-full ${C.btnBg} ${C.btnHover} text-white py-3 rounded font-semibold
    transition-all duration-150 ease-in-out focus:outline-none focus:ring-2 ${C.ring}
    focus:ring-offset-2 ${isLight ? 'focus:ring-offset-white' : 'focus:ring-offset-neutral-900'}
    cursor-pointer active:scale-95 disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2
  `
  const feedbackMessageContainerClasses = (status: FormStatus) => `
    p-3 rounded-md text-sm flex items-start gap-2 border
    transition-all duration-300 ease-in-out
    ${status === 'success' ? `${C.bgSuccess} ${C.textSuccess} ${C.borderSuccess}` : ''}
    ${status === 'error' ? `${C.bgError} ${C.textError} ${C.borderError}` : ''}
    ${status === 'idle' || status === 'submitting' ? 'opacity-0 max-h-0 py-0 border-transparent pointer-events-none' : 'opacity-100 max-h-40 py-3'}
  `

  const SuccessIcon = () => (
    <svg className={`w-5 h-5 flex-shrink-0 ${C.iconSuccess}`} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
    </svg>
  );
  const ErrorIcon = () => (
    <svg className={`w-5 h-5 flex-shrink-0 ${C.iconError}`} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
    </svg>
  );
   const LoadingSpinnerIcon = () => (
    <svg className="animate-spin -ml-1 mr-2 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
  );

  return (
    <form onSubmit={handleSubmit(onSubmit)} className={wrapperClass} noValidate>
      <input type="text" tabIndex={-1} className="hidden" {...register('website')} />
      <input type="hidden" value={newsletterSlug} {...register('newsletter')} />

      {/* Email + Postcode group: Bottom padding is now conditional */}
      {/* pb-4 (1rem) if errors.email or errors.postcode exist, to make space for the absolute error messages. */}
      {/* pb-0 if no errors in this group, allowing space-y-4 on form to control gap to next section. */}
      <div className={`flex flex-col sm:flex-row gap-4 relative ${hasInputGroupErrors ? 'pb-4' : 'pb-0'}`}>
        <div className="flex-1 relative">
          <label className="sr-only" htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            {...emailFieldRestPropsFromRHF}
            ref={(e: HTMLInputElement | null) => {
              emailFieldRefFromRHF(e);
              emailInputRef.current = e;
            }}
            placeholder="Your email address"
            className={getInputClasses(!!errors.email)}
            aria-invalid={errors.email ? 'true' : 'false'}
            disabled={formStatus === 'submitting'}
            onFocus={handleInteraction}
            onInput={handleInteraction}
          />
          {errors.email && (
            <p className="absolute left-0 top-full mt-1 text-xs text-red-500 dark:text-red-400">
              {errors.email.message}
            </p>
          )}
        </div>

        <div className="relative w-full sm:w-[170px] flex-shrink-0">
          <label className="sr-only" htmlFor="postcode">Postcode</label>
          <input
            id="postcode"
            {...register('postcode')}
            placeholder="Postcode"
            className={getInputClasses(!!errors.postcode, 'pr-8')}
            aria-invalid={errors.postcode ? 'true' : 'false'}
            disabled={formStatus === 'submitting'}
            onFocus={handleInteraction}
            onInput={handleInteraction}
          />
          <button
            type="button"
            className="absolute inset-y-0 right-0 flex items-center pr-3 group cursor-help focus:outline-none"
            aria-label="Why we ask for your postcode"
            disabled={formStatus === 'submitting'}
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"
              strokeWidth={1.5} stroke="currentColor" className={tooltipIconClasses} aria-hidden="true" >
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z" />
            </svg>
            <span role="tooltip" className={tooltipTextClasses}>
              We use your postcode to find relevant events happening near you.
            </span>
          </button>
          {errors.postcode && (
            <p className="absolute right-0 top-full mt-1 max-w-[170px] text-xs text-red-500 dark:text-red-400 text-right">
              {errors.postcode.message}
            </p>
          )}
        </div>
      </div>

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
                  <label className={`group ${formStatus === 'submitting' ? 'cursor-not-allowed opacity-70' : 'cursor-pointer'}`}>
                    <input
                      type="checkbox"
                      value={tag}
                      checked={isChecked}
                      className="peer hidden"
                      onChange={() => toggleTag(tag)}
                      aria-labelledby={`interest-label-${tag}`}
                      disabled={formStatus === 'submitting'}
                    />
                    <span
                      id={`interest-label-${tag}`}
                      className={isChecked ? selectedPillClasses : unselectedPillClasses}
                    >
                      {tag}
                    </span>
                    {burst === tag && Array.from({ length: 12 }).map((_, i) => {
                      const angle = Math.random() * 360; const dist  = 20 + Math.random() * 15;
                      const dx    = Math.cos(angle) * dist; const dy    = Math.sin(angle) * dist;
                      const size  = 2 + Math.random() * 2; const confettiColor = confettiColors[Math.floor(Math.random() * confettiColors.length)];
                      return (
                        <div key={i} style={{ '--dx': `${dx}px`, '--dy': `${dy}px`, '--angle': `${Math.random()*360}deg`, left: '50%', top: '40%', width: `${size}px`, height: `${size * 2}px`, animationDelay:`${Math.random()*0.04}s` } as React.CSSProperties}
                          className={`absolute pointer-events-none animate-[tiny-confetti-pop_0.6s_ease-out_forwards] ${confettiColor}`} />
                      )
                    })}
                  </label>
                </div>
              )
            })}
          </div>
          {errors.interests && (
            <p className="text-xs text-red-500 dark:text-red-400 mt-1">{errors.interests.message}</p>
          )}
        </div>
      ) : (
         <input type="hidden" value={singleInterest ?? ''} {...register('interests')} />
      )}

      <div>
        <Turnstile
          ref={turnstileRef}
          siteKey={process.env.NEXT_PUBLIC_CF_SITE_KEY!}
          onSuccess={setToken}
          options={{ theme: mode } as TurnstileProps['options']}
          onExpire={() => {
            setValue('cfToken', '', { shouldValidate: true });
          }}
          onError={() => {
            // Optional: setFormStatus('error');
            // Optional: setFormMessage('Captcha challenge failed. Please try again.');
          }}
        />
        {errors.cfToken && (
          <p className="text-xs text-red-500 dark:text-red-400 mt-1">{errors.cfToken.message}</p>
        )}
      </div>

      <div
        className={feedbackMessageContainerClasses(formStatus)}
        role="alert"
        aria-live={formStatus === 'error' ? "assertive" : "polite"}
      >
        {formStatus === 'success' && <SuccessIcon />}
        {formStatus === 'error' && <ErrorIcon />}
        <span>{formMessage}</span>
      </div>

      <button type="submit" className={ctaButtonClasses} disabled={formStatus === 'submitting' || isSubmitting}>
        {formStatus === 'submitting' && <LoadingSpinnerIcon />}
        {formStatus === 'submitting' ? 'Submitting...' : ctaText}
      </button>
    </form>
  )
}
