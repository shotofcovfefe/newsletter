import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@supabase/supabase-js'
import { Redis } from '@upstash/redis'
import { Ratelimit } from '@upstash/ratelimit'
import { Resend } from 'resend'
import crypto from 'node:crypto'
import * as z from 'zod'

/* ── Supabase ───────────────────── */
const supabase = createClient(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_KEY!
)

/* ── Mailgun ────────────────────── */
const resend = new Resend(process.env.RESEND_API_KEY!)

/* ── Upstash Redis + Rate-limit ─── */
const redis = new Redis({
  url  : process.env.UPSTASH_REDIS_REST_URL!,
  token: process.env.UPSTASH_REDIS_REST_TOKEN!,
})

const ratelimit = new Ratelimit({
  redis,
  limiter: Ratelimit.fixedWindow(5, '10 m'),   // 5 hits / 10 min per IP
})

/* ── Zod schema (same as client) ─ */
const interestTags = [
  'Art','Food & Drink','Live Music','Workshops',
  'Comedy','Markets','Families','Date Night','Solo Friendly',
] as const

const ukPostcode =
  /^([A-Z]{1,2}\d[A-Z\d]? ?\d[ABD-HJLNP-UW-Z]{2})$/i

const schema = z.object({
  email    : z.string().email(),
  postcode : z.string().regex(ukPostcode),
  interests: z.array(z.enum(interestTags)),
  website  : z.string().max(0).optional(),   // honeypot
  cfToken  : z.string(),
})

/* ── Turnstile verify helper ─────── */
async function verifyTurnstile(token:string, ip:string) {
  const body = new URLSearchParams({
    secret  : process.env.CF_SECRET_KEY!,
    response: token,
    remoteip: ip,
  })
  const res = await fetch(
    'https://challenges.cloudflare.com/turnstile/v0/siteverify',
    { method:'POST', body }
  ).then(r=>r.json())
  return res.success === true
}

/* ── POST /api/subscribe ─────────── */
export async function POST(req: NextRequest) {
  /* rate-limit by IP */
  const ipHeader = req.headers.get('x-forwarded-for') ?? ''
  const ip = (ipHeader.split(',')[0] || req.ip || 'unknown').trim()

  const { success } = await ratelimit.limit(ip)
  if (!success)
    return NextResponse.json({ error:'Too many requests' }, { status:429 })

  /* parse & validate body */
  const parsed = schema.safeParse(await req.json())
  if (!parsed.success)
    return NextResponse.json({ error:'Bad data' }, { status:400 })

  const { email, postcode, interests, cfToken } = parsed.data

  /* Turnstile captcha */
  if (!(await verifyTurnstile(cfToken, ip)))
    return NextResponse.json({ error:'captcha' }, { status:400 })

  /* write to Supabase */
  const token = crypto.randomBytes(32).toString('hex')          // ➕ generate

    const { error } = await supabase
      .from('email_subscribers')
      .upsert({ email, postcode, interests, confirm_token: token, confirmed: false })

    if (error)
      return NextResponse.json({ error:'db' }, { status:500 })

    /* confirmation link */
    const confirmLink = `${process.env.NEXT_PUBLIC_URL}/confirm?email=${encodeURIComponent(email)}&token=${token}`

    const FROM_ADDR =
      process.env.IS_DEV === true
        ? 'onboarding@resend.dev'
        : 'hello@unfog.london'


    /* send double-opt-in email via Resend */
    try {
  const { error: mailError } = await resend.emails.send({
    from: 'unfog.london <hello@unfog.london>'
    to:   email,
    subject: 'Confirm your subscription',
    html:  `Click <a href="${confirmLink}">here</a> to confirm.`,
  })

  if (mailError) {
    console.error('Resend API error →', mailError)
    return NextResponse.json({ error: 'mail' }, { status: 500 })
  }
} catch (err) {
  console.error('Resend threw →', err)
  return NextResponse.json({ error: 'mail' }, { status: 500 })
}

  return NextResponse.json({ ok: true })
}
