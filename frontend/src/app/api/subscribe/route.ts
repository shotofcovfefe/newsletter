import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { Redis } from '@upstash/redis';
import { Ratelimit } from '@upstash/ratelimit';
import { Resend } from 'resend';
import crypto from 'node:crypto';

import { generateConfirmationEmailContent, templates } from '@/lib/emailTemplates';
import { subscriptionSchema } from '@/lib/validation';

/* --- Supabase Client --- */
const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
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
  limiter: Ratelimit.fixedWindow(5, '10 m'),
});


/* --- Turnstile Verification Helper --- */
async function verifyTurnstile(token: string, ip: string): Promise<boolean> {
    if (!process.env.CF_SECRET_KEY) {
        console.error("Missing Cloudflare Secret Key (CF_SECRET_KEY)");
        return false;
    }
    const body = new URLSearchParams({
        secret:   process.env.CF_SECRET_KEY,
        response: token,
        remoteip: ip,
    });
    try {
        const response = await fetch(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            { method:'POST', body }
        );
        if (!response.ok) {
             console.error(`Turnstile verification failed with status: ${response.status}`);
             return false;
        }
        const data = await response.json();
        return data.success === true;
    } catch (error) {
        console.error("Error verifying Turnstile token:", error);
        return false;
    }
}


/* --- MAIN API ROUTE: POST /api/subscribe --- */
export async function POST(req: NextRequest) {

  /* 1. Get Client IP Address for Rate Limiting */
  const ipHeader = req.headers.get('x-forwarded-for');
  const ip = (ipHeader ? ipHeader.split(',')[0]?.trim() : null) ?? 'unknown';

  if (ip === 'unknown') {
      console.warn("Could not determine client IP address for rate limiting.");
  }

  /* 2. Apply Rate Limiting */
  const { success: rateLimitSuccess } = await ratelimit.limit(ip);
  if (!rateLimitSuccess) {
    return NextResponse.json({ error: 'Too many requests. Please try again later.' }, { status: 429 });
  }

  /* 3. Parse and Validate Request Body */
  let jsonData;
  try {
    jsonData = await req.json();
  } catch (error) {
    return NextResponse.json({ error: 'Invalid request format.' }, { status: 400 });
  }

  // Use the imported subscriptionSchema here
  const parsed = subscriptionSchema.safeParse(jsonData);

  if (!parsed.success) {
    console.warn("Subscription validation failed:", parsed.error.flatten());
    const postcodeError = parsed.error.flatten().fieldErrors.postcode?.[0];
    return NextResponse.json({
        error: postcodeError || 'Invalid data provided.',
        details: parsed.error.flatten().fieldErrors
    }, { status: 400 });
  }

  /* 4. Check Honeypot Field */
  if (parsed.data.website) {
      console.log(`Honeypot triggered for submission.`);
      return NextResponse.json({ ok: true });
  }

const { email, postcode, interests, cfToken, newsletter } = parsed.data;

  /* 5. Verify Cloudflare Turnstile Captcha */
  if (!(await verifyTurnstile(cfToken, ip))) {
    console.warn(`Turnstile verification failed for IP: ${ip}, Email: ${email}`);
    return NextResponse.json({ error: 'Captcha verification failed. Please refresh and try again.' }, { status: 400 });
  }

  /* 6. Generate Confirmation and Unsubscribe Tokens & Upsert Subscriber into Database */
  const confirmToken = crypto.randomBytes(32).toString('hex');
  const unsubscribeToken = crypto.randomBytes(32).toString('hex');

  const { error: dbError } = await supabase
    .from('email_subscribers')
    .upsert(
      {
          email: email,
          postcode: postcode,
          interests: interests,
          confirm_token: confirmToken,
          unsubscribe_token: unsubscribeToken,
          confirmed: false,
          unsubscribed: false
      },
      { onConflict: 'email' }
    );

  if (dbError) {
    console.error("Supabase upsert error:", dbError);
    return NextResponse.json({ error: 'An internal error occurred saving subscription data.' }, { status: 500 });
  }

  /* 7. Prepare and Send Confirmation Email */
  const confirmLink = `${process.env.NEXT_PUBLIC_URL}/confirm?email=${encodeURIComponent(email)}&token=${confirmToken}`;
  const { html: emailHtml, text: emailText } =
    generateConfirmationEmailContent(confirmLink, newsletter as keyof typeof templates);
  const emailSubject =
    templates[newsletter as keyof typeof templates]?.subject
    ?? templates.default.subject;
  const FROM_ADDR = process.env.IS_DEV === 'true' ? 'onboarding@resend.dev' : 'hello@unfog.london';

  try {
    const { error: mailError } = await resend.emails.send({
      from:    `Unfog London <${FROM_ADDR}>`,
      to:      email,
      subject: emailSubject,
      html:    emailHtml,
      text:    emailText,
    });

    if (mailError) {
      console.error(`Resend API error sending confirmation to ${email}:`, mailError);
      return NextResponse.json({ error: 'Failed to send confirmation email.' }, { status: 500 });
    }
  } catch (err: any) {
    console.error(`Resend threw an unexpected error for ${email}:`, err?.message || err);
    return NextResponse.json({ error: 'Failed to send confirmation email due to an unexpected error.' }, { status: 500 });
  }

  /* 8. Return Success Response to Frontend */
  return NextResponse.json({ ok: true });
}