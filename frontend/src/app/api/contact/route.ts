// src/app/api/contact/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { Resend } from 'resend';
import * as z from 'zod';
import { Ratelimit } from '@upstash/ratelimit';
import { Redis } from '@upstash/redis';

// --- Zod Schema (should match client-side schema) ---
const contactFormSchema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters'),
  email: z.string().email('Please enter a valid email address'),
  subject: z.string().min(3, 'Subject must be at least 3 characters').optional(),
  message: z.string().min(10, 'Message must be at least 10 characters'),
  cfToken: z.string().min(1, { message: "Captcha completion required" }),
});

// --- Initialize Resend ---
const resend = new Resend(process.env.RESEND_API_KEY);
const contactRecipientEmail = process.env.CONTACT_FORM_RECIPIENT_EMAIL; // Your email, e.g., andy@unfog.london or madame.clown.art@gmail.com
const fromAddress = process.env.CONTACT_FORM_FROM_EMAIL || 'contact@unfog.london'; // A verified sending email on your domain

// --- Upstash Redis + Rate-limit --- (Copied from subscribe route, adjust as needed)
const redis = new Redis({
  url:   process.env.UPSTASH_REDIS_REST_URL!,
  token: process.env.UPSTASH_REDIS_REST_TOKEN!,
});
const ratelimit = new Ratelimit({
  redis,
  limiter: Ratelimit.fixedWindow(3, '10 m'), // Allow 3 contact attempts per IP per 10 minutes
});

// --- Turnstile Verification Helper (Copied from subscribe route) ---
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
        const response = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', { method:'POST', body });
        if (!response.ok) {
             console.error(`Turnstile verification failed status: ${response.status}`); return false;
        }
        const data = await response.json();
        return data.success === true;
    } catch (error) { console.error("Error verifying Turnstile token:", error); return false; }
}

export async function POST(req: NextRequest) {
  if (!contactRecipientEmail) {
    console.error('CONTACT_FORM_RECIPIENT_EMAIL is not set in environment variables.');
    return NextResponse.json({ error: 'Server configuration error.' }, { status: 500 });
  }

  /* 1. Rate Limiting */
  const ipHeader = req.headers.get('x-forwarded-for');
  const ip = (ipHeader ? ipHeader.split(',')[0]?.trim() : null) ?? 'unknown';
  if (ip === 'unknown') { console.warn("Could not determine client IP for rate limiting contact form."); }
  const { success: rateLimitSuccess } = await ratelimit.limit(ip);
  if (!rateLimitSuccess) {
    return NextResponse.json({ error: 'Too many requests. Please try again later.' }, { status: 429 });
  }

  /* 2. Parse and Validate Body */
  let jsonData;
  try {
    jsonData = await req.json();
  } catch (error) {
    return NextResponse.json({ error: 'Invalid request format.' }, { status: 400 });
  }
  const parsed = contactFormSchema.safeParse(jsonData);

  if (!parsed.success) {
    console.warn("Contact form validation failed:", parsed.error.flatten());
    return NextResponse.json({ error: 'Invalid data provided.', details: parsed.error.flatten().fieldErrors }, { status: 400 });
  }

  const { name, email, subject, message, cfToken } = parsed.data;

  /* 3. Verify Turnstile */
  if (!(await verifyTurnstile(cfToken, ip))) {
    console.warn(`Turnstile verification failed for contact form IP: ${ip}, Email: ${email}`);
    return NextResponse.json({ error: 'Captcha verification failed. Please try again.' }, { status: 400 });
  }

  /* 4. Send Email via Resend */
  try {
    await resend.emails.send({
      from:    `Contact Form <${fromAddress}>`, // Must be a verified domain in Resend
      to:      contactRecipientEmail,          // Your email address to receive messages
      replyTo: email,                          // <-- CORRECTED: Changed from reply_to to replyTo
      subject: subject ? `Contact Form: ${subject}` : `New Contact from ${name} via Unfog London`,
      html: `
        <p>You received a new message from your Unfog London contact form:</p>
        <p><strong>Name:</strong> ${name}</p>
        <p><strong>Email:</strong> ${email}</p>
        ${subject ? `<p><strong>Subject:</strong> ${subject}</p>` : ''}
        <p><strong>Message:</strong></p>
        <p>${message.replace(/\n/g, '<br>')}</p>
      `,
      text: `
        New message from Unfog London contact form:
        Name: ${name}
        Email: ${email}
        ${subject ? `Subject: ${subject}` : ''}
        Message:
        ${message}
      `,
    });

    // Optional: Send an auto-reply to the user
    await resend.emails.send({
      from: `Unfog London <${fromAddress}>`,
      to: email,
      subject: "Thanks for reaching out to Unfog London!",
      html: `<p>Hi ${name},</p><p>Thanks for your message. I've received it and will get back to you as soon as possible.</p><p>Best,<br/>Andy @ Unfog London</p>`,
    });

    return NextResponse.json({ success: true, message: 'Message sent successfully!' });

  } catch (error: any) {
    console.error('Resend API error (contact form):', error);
    return NextResponse.json({ error: 'Failed to send message due to a server error.' }, { status: 500 });
  }
}