// /src/app/api/subscribe/route.ts

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { Redis } from '@upstash/redis';
import { Ratelimit } from '@upstash/ratelimit';
import { Resend } from 'resend';
import crypto from 'node:crypto';
import * as z from 'zod';

// Import the email template generator function using path alias
import { generateConfirmationEmailContent } from '@/lib/emailTemplates';

/* --- Supabase Client --- */
// Ensure environment variables are configured
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
  limiter: Ratelimit.fixedWindow(5, '10 m'), // Allow 5 requests per IP per 10 minutes
});

/* --- Zod Schema (should match client-side schema) --- */
// Ensure these tags match exactly what's used in your SignupForm component
const interestTags = [
  'Art', 'Food & Drink', 'Live Music', 'Workshops',
  'Comedy', 'Markets', 'Families', 'Date Night', 'Solo Friendly'
] as const;
// Regex for UK postcodes
const ukPostcode = /^([A-Z]{1,2}\d[A-Z\d]? ?\d[ABD-HJLNP-UW-Z]{2})$/i;

const schema = z.object({
  email:     z.string().email("Invalid email address"),
  postcode:  z.string().trim().regex(ukPostcode, 'Invalid UK postcode'),
  interests: z.array(z.enum(interestTags)).min(1, 'Please select at least one interest'),
  website:   z.string().max(0, { message: "Bots only" }).optional(), // Honeypot field
  cfToken:   z.string().min(1, { message: "Captcha completion required" }), // Cloudflare Turnstile token
});

/* --- Turnstile Verification Helper --- */
async function verifyTurnstile(token: string, ip: string): Promise<boolean> {
    // Ensure Cloudflare Secret Key is set
    if (!process.env.CF_SECRET_KEY) {
        console.error("Missing Cloudflare Secret Key (CF_SECRET_KEY)");
        return false;
    }
    const body = new URLSearchParams({
        secret:   process.env.CF_SECRET_KEY,
        response: token,
        remoteip: ip, // Send IP address to Cloudflare
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
        return false; // Assume failure on fetch error
    }
}


/* --- MAIN API ROUTE: POST /api/subscribe --- */
export async function POST(req: NextRequest) {

  /* 1. Get Client IP Address for Rate Limiting */
  // Use 'x-forwarded-for' header (standard for proxies/Vercel)
  const ipHeader = req.headers.get('x-forwarded-for');
  // Extract the first IP, trim whitespace, default to 'unknown' if header missing/malformed
  const ip = (ipHeader ? ipHeader.split(',')[0]?.trim() : null) ?? 'unknown';

  // Handle cases where IP couldn't be determined (important for rate limiting)
  if (ip === 'unknown') {
      console.warn("Could not determine client IP address for rate limiting.");
      // Optional: Return an error if IP is strictly required
      // return NextResponse.json({ error: 'Could not identify request source.' }, { status: 400 });
  }

  /* 2. Apply Rate Limiting */
  const { success: rateLimitSuccess, remaining } = await ratelimit.limit(ip);
  // console.log(`Rate limit check for IP ${ip}: ${rateLimitSuccess}, remaining: ${remaining}`); // Debug logging
  if (!rateLimitSuccess) {
    // Send standard "Too Many Requests" response
    return NextResponse.json({ error: 'Too many requests. Please try again later.' }, { status: 429 });
  }

  /* 3. Parse and Validate Request Body */
  let jsonData;
  try {
    jsonData = await req.json();
  } catch (error) {
    // Handle cases where request body isn't valid JSON
    return NextResponse.json({ error: 'Invalid request format.' }, { status: 400 });
  }
  const parsed = schema.safeParse(jsonData);

  // If validation fails, return specific errors
  if (!parsed.success) {
    console.warn("Subscription validation failed:", parsed.error.flatten()); // Log server-side
    return NextResponse.json({ error: 'Invalid data provided.', details: parsed.error.flatten().fieldErrors }, { status: 400 });
  }

  /* 4. Check Honeypot Field */
  // If the hidden 'website' field is filled out, it's likely a bot
  if (parsed.data.website) {
      console.log(`Honeypot triggered for submission.`);
      // Return a generic success response to not alert the bot
      return NextResponse.json({ ok: true });
  }

  // Destructure validated data
  const { email, postcode, interests, cfToken } = parsed.data;

  /* 5. Verify Cloudflare Turnstile Captcha */
  if (!(await verifyTurnstile(cfToken, ip))) {
    console.warn(`Turnstile verification failed for IP: ${ip}, Email: ${email}`);
    return NextResponse.json({ error: 'Captcha verification failed. Please refresh and try again.' }, { status: 400 });
  }

  /* 6. Generate Confirmation Token & Upsert Subscriber into Database */
  const token = crypto.randomBytes(32).toString('hex'); // Secure random token
  const { error: dbError } = await supabase
    .from('email_subscribers')
    .upsert( // Using upsert handles new signups and re-sends confirmation for existing unconfirmed emails
      {
          email: email,
          postcode: postcode,
          interests: interests,
          confirm_token: token,
          confirmed: false // Always set to false initially
      },
      { onConflict: 'email' } // If email exists, update the record (e.g., new token/interests)
    );

  // Handle database errors
  if (dbError) {
    console.error("Supabase upsert error:", dbError);
    // Avoid exposing detailed database errors to the client
    return NextResponse.json({ error: 'An internal error occurred saving subscription data.' }, { status: 500 });
  }

  /* 7. Prepare and Send Confirmation Email */
  // Construct the unique confirmation link for this user
  const confirmLink = `${process.env.NEXT_PUBLIC_URL}/confirm?email=${encodeURIComponent(email)}&token=${token}`;

  // Get the formatted email content (HTML and Text)
  const { html: emailHtml, text: emailText } = generateConfirmationEmailContent(confirmLink);
  const emailSubject = 'Confirm your Unfog London subscription'; // Consistent subject

  // Determine the 'from' address based on environment
  const FROM_ADDR =
    process.env.IS_DEV === 'true'
      ? 'onboarding@resend.dev' // Resend's testing address (limited sending)
      : 'hello@unfog.london';   // Your verified production domain address

  try {
    // Attempt to send the email using Resend
    const { data, error: mailError } = await resend.emails.send({
      from:    `Unfog London <${FROM_ADDR}>`, // Sender name and address
      to:      email,                         // Recipient's email
      subject: emailSubject,                  // Email subject
      html:    emailHtml,                     // HTML version of the email
      text:    emailText,                     // Plain text version
    });

    // Handle errors specifically from the Resend API
    if (mailError) {
      console.error(`Resend API error sending confirmation to ${email}:`, mailError);
      // Return a generic server error status
      return NextResponse.json({ error: 'Failed to send confirmation email.' }, { status: 500 });
    }
     // console.log(`Confirmation email sent successfully to ${email}, Resend ID:`, data?.id); // Optional success logging

  } catch (err: any) {
    // Catch unexpected errors during the email sending process
    console.error(`Resend threw an unexpected error for ${email}:`, err?.message || err);
    return NextResponse.json({ error: 'Failed to send confirmation email due to an unexpected error.' }, { status: 500 });
  }

  /* 8. Return Success Response to Frontend */
  // Let the frontend know the initial submission was successful
  return NextResponse.json({ ok: true });
}