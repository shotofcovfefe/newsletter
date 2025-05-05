// /app/api/subscribe/route.ts

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { Redis } from '@upstash/redis';
import { Ratelimit } from '@upstash/ratelimit';
import { Resend } from 'resend';
import crypto from 'node:crypto';
import * as z from 'zod';

// Import the email template generator function
import { generateConfirmationEmailContent } from '../../../lib/emailTemplates';

/* --- Supabase Client --- */
const supabase = createClient(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_KEY!
);

/* --- Resend Client --- */
const resend = new Resend(process.env.RESEND_API_KEY!);

/* --- Upstash Redis + Rate-limit --- */
const redis = new Redis({
  url:   process.env.UPSTASH_REDIS_REST_URL!,
  token: process.env.UPSTASH_REDIS_REST_TOKEN!,
});
const ratelimit = new Ratelimit({
  redis,
  limiter: Ratelimit.fixedWindow(5, '10 m'), // 5 hits / 10 min per IP
});

/* --- Zod Schema (sync with client) --- */
const interestTags = [
  'Art', 'Food & Drink', 'Live Music', 'Workshops',
  'Comedy', 'Markets', 'Families', 'Date Night', 'Solo Friendly'
] as const; // Ensure your actual tags are listed here
const ukPostcode = /^([A-Z]{1,2}\d[A-Z\d]? ?\d[ABD-HJLNP-UW-Z]{2})$/i;
const schema = z.object({
  email:     z.string().email(),
  postcode:  z.string().trim().regex(ukPostcode, 'Invalid postcode'), // Added trim() and message
  interests: z.array(z.enum(interestTags)).min(1, 'Pick at least one tag'), // Added min length validation
  website:   z.string().max(0, { message: "Bots only" }).optional(), // Honeypot with message
  cfToken:   z.string().min(1, { message: "Captcha token required" }), // Added min length validation
});

/* --- Turnstile Verification Helper --- */
async function verifyTurnstile(token: string, ip: string) {
    const body = new URLSearchParams({
        secret  : process.env.CF_SECRET_KEY!,
        response: token,
        remoteip: ip,
    });
    try {
        const res = await fetch(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            { method:'POST', body }
        ).then(r=>r.json());
        return res.success === true;
    } catch (error) {
        console.error("Turnstile verification fetch error:", error);
        return false; // Assume failure on fetch error
    }
}

/* --- POST /api/subscribe --- */
export async function POST(req: NextRequest) {
  /* Rate-limit by IP */
  const ipHeader = req.headers.get('x-forwarded-for') ?? req.ip ?? 'unknown'; // More robust IP fetching
  const ip = ipHeader.split(',')[0]?.trim() || 'unknown';
  const { success: rateLimitSuccess, remaining } = await ratelimit.limit(ip);
  // console.log(`Rate limit check for IP ${ip}: ${rateLimitSuccess}, remaining: ${remaining}`); // Optional logging
  if (!rateLimitSuccess) {
    return NextResponse.json({ error: 'Too many requests. Please try again later.' }, { status: 429 });
  }

  /* Parse & validate body */
  let jsonData;
  try {
    jsonData = await req.json();
  } catch (error) {
    return NextResponse.json({ error: 'Invalid request body.' }, { status: 400 });
  }
  const parsed = schema.safeParse(jsonData);

  if (!parsed.success) {
    console.warn("Subscription validation failed:", parsed.error.flatten()); // Log validation errors
    return NextResponse.json({ error: 'Invalid data provided.', details: parsed.error.flatten().fieldErrors }, { status: 400 });
  }

  // Honeypot check
  if (parsed.data.website) {
      console.log(`Honeypot triggered for email: ${parsed.data.email}`);
      // Still return OK to not alert the bot, but don't proceed
      return NextResponse.json({ ok: true });
  }

  const { email, postcode, interests, cfToken } = parsed.data;

  /* Turnstile captcha */
  if (!(await verifyTurnstile(cfToken, ip))) {
    console.warn(`Turnstile verification failed for IP: ${ip}, Email: ${email}`);
    return NextResponse.json({ error: 'Captcha verification failed. Please try again.' }, { status: 400 });
  }

  /* Write to Supabase */
  const token = crypto.randomBytes(32).toString('hex');
  const { error: dbError } = await supabase
    .from('email_subscribers')
    .upsert( // Using upsert handles both new and existing unconfirmed signups
      { email, postcode, interests, confirm_token: token, confirmed: false },
      { onConflict: 'email' } // Update if email exists
    );

  if (dbError) {
    console.error("Supabase upsert error:", dbError);
    // Avoid exposing detailed DB errors to the client
    return NextResponse.json({ error: 'An internal error occurred. Please try again later.' }, { status: 500 });
  }

  /* Confirmation link */
  const confirmLink = `${process.env.NEXT_PUBLIC_URL}/confirm?email=${encodeURIComponent(email)}&token=${token}`;

  /* --- Get Email Content using the imported function --- */
  const { html: emailHtml, text: emailText } = generateConfirmationEmailContent(confirmLink);
  const emailSubject = 'Confirm your Unfog London subscription'; // Consistent subject

  const FROM_ADDR =
    process.env.IS_DEV === 'true'
      ? 'onboarding@resend.dev' // Use Resend's test address for development
      : 'hello@unfog.london';   // Your verified production address

  /* Send double-opt-in email via Resend */
  try {
    const { data, error: mailError } = await resend.emails.send({
      from:    `Unfog London <${FROM_ADDR}>`, // Consistent sender name
      to:      email,
      subject: emailSubject,
      html:    emailHtml, // Use generated HTML
      text:    emailText, // Use generated Text
    });

    if (mailError) {
      // Log detailed error server-side
      console.error(`Resend API error sending confirmation to ${email}:`, mailError);
      return NextResponse.json({ error: 'Failed to send confirmation email.' }, { status: 500 });
    }
     // console.log(`Confirmation email sent successfully to ${email}, ID:`, data?.id); // Optional success logging

  } catch (err: any) {
    // Log detailed error server-side
    console.error(`Resend threw an unexpected error for ${email}:`, err?.message || err);
    return NextResponse.json({ error: 'Failed to send confirmation email due to an unexpected error.' }, { status: 500 });
  }

  // Return success to the frontend
  return NextResponse.json({ ok: true });
}