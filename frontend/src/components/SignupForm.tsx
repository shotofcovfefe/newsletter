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
  email    : z.string().email(),
  postcode : z.string().trim().regex(ukPostcode, 'Invalid postcode'),
  interests: z.array(z.enum(interestTags)).min(1, 'Pick at least one tag'),
  website  : z.string().max(0).optional(),   // honeypot
  cfToken  : z.string(),                     // Turnstile token
})
type FormData = z.infer<typeof schema>

/* ------------ component ------------ */
export default function SignupForm() {
  const [burst, setBurst] = useState<string | null>(null)

  /* react-hook-form */
  const { register, handleSubmit, watch, setValue } = useForm<FormData>({
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
    current.has(tag) ? current.delete(tag) : current.add(tag)
    setValue('interests', Array.from(current) as any)
    if (!current.has(tag)) return;
    setBurst(tag)
    setTimeout(()=>setBurst(null), 600)
  }

  /* submit handler → call API */
  const onSubmit = async (data:FormData) => {
    const r = await fetch('/api/subscribe', {
      method :'POST',
      headers:{ 'Content-Type':'application/json' },
      body   : JSON.stringify(data),
    })
    if (r.ok) alert('Check your inbox to confirm!')
    else      alert('Error – please try again')
  }

  /* Turnstile token setter */
  const setToken = (token:string|null) => {
    setValue('cfToken', token || '')
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="bg-white dark:bg-neutral-900 shadow-md rounded-xl px-6 py-8 space-y-6
                 text-left max-w-xl w-full"
    >
      {/* honeypot - keeps bots at bay but invisible */}
      <input type="text" tabIndex={-1} className="hidden" {...register('website')} />

      {/* Turnstile widget (invisible style keeps look identical) */}
      <Turnstile
        siteKey={process.env.NEXT_PUBLIC_CF_SITE_KEY!}
        onSuccess={setToken}
        className="mb-4"
        theme="dark"
      />

      {/*  ---- Email + Postcode ---- */}
      <div className="flex flex-col sm:flex-row gap-4">
        <label className="sr-only" htmlFor="email">Email</label>
        <input
          id="email"
          {...register('email')}
          placeholder="Your email address"
          className="flex-1 p-3 rounded border border-neutral-300 dark:border-neutral-700
                     dark:bg-neutral-800 dark:text-white focus:outline-none
                     focus:ring-4 focus:ring-black/20"
        />
        <label className="sr-only" htmlFor="postcode">Postcode</label>
        <input
          id="postcode"
          {...register('postcode')}
          placeholder="Postcode"
          className="p-3 w-full sm:w-40 rounded border border-neutral-300 dark:border-neutral-700
                     dark:bg-neutral-800 dark:text-white focus:outline-none
                     focus:ring-4 focus:ring-black/20"
        />
      </div>

      {/* ---- Interest pills (unchanged visuals) ---- */}
      <div>
        <span className="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-400">
          What are you into?
        </span>
        <div className="flex flex-wrap gap-2">
          {interestTags.map(tag => (
            <div key={tag} className="relative">
              <label className="cursor-pointer">
                <input
                  type="checkbox"
                  value={tag}
                  {...register('interests')}
                  className="peer hidden"
                  onChange={()=>toggleTag(tag)}
                />
                <span className="
                  inline-block px-3 py-1 border border-neutral-300 dark:border-neutral-600
                  rounded-full text-sm transition
                  peer-checked:bg-emerald-500 peer-checked:text-white
                  hover:border-neutral-500 dark:hover:border-neutral-400
                  active:scale-95
                ">
                  {tag}
                </span>
              </label>

              {/* confetti spark (unchanged) */}
              {burst === tag && Array.from({ length: 12 }).map((_, i) => {
                const angle = Math.random()*360
                const dist  = 20+Math.random()*15
                const dx    = Math.cos(angle)*dist
                const dy    = Math.sin(angle)*dist
                const size  = 2+Math.random()*2
                const color = confettiColors[Math.floor(Math.random()*confettiColors.length)]
                return (
                  <div key={i}
                    style={{
                      '--dx':`${dx}px`, '--dy':`${dy}px`,
                      '--angle':`${Math.random()*360}deg`,
                      left:'50%', top:'40%',
                      width:`${size}px`,height:`${size*2}px`,
                      animationDelay:`${Math.random()*0.04}s`,
                    } as React.CSSProperties}
                    className={`absolute pointer-events-none
                      animate-[tiny-confetti-pop_0.6s_ease-out_forwards] ${color}`}
                  />
                )
              })}
            </div>
          ))}
        </div>
      </div>

      {/* CTA (colour unchanged) */}
      <button
        type="submit"
        className="w-full bg-emerald-500 hover:bg-emerald-600 text-white
                   py-3 rounded font-semibold transition">
        Subscribe
      </button>
    </form>
  )
}
