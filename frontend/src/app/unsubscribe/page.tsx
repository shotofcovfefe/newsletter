// src/app/unsubscribe/page.tsx
import { createClient } from '@supabase/supabase-js';
import Link from 'next/link';
import { Suspense } from 'react';

// Initialize Supabase client (ensure these env vars are available server-side)
// This should ideally be in a shared lib file, but for simplicity here:
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseKey) {
  // In a real app, you might throw an error or have a fallback,
  // but for page rendering, console logging is a start.
  // The component itself will handle the Supabase client initialization.
  console.error("Supabase URL or Key is not defined in environment variables for unsubscribe page.");
}


// Define the props type expected by the UnsubscribeHandler component
interface UnsubscribeHandlerProps {
    token?: string;
}

// --- Core Unsubscribe Logic Component ---
async function UnsubscribeHandler({ token }: UnsubscribeHandlerProps) {
  let status: 'success' | 'error' | 'invalid' | 'already_unsubscribed' = 'invalid';
  let message: string = 'Invalid unsubscribe link provided.'; // Default message

  // Ensure Supabase client is initialized correctly within the async component
  const supabase = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!);

  if (!token) {
    status = 'invalid';
    message = 'Unsubscribe token is missing. Please use the link from your email.';
  } else {
    try {
      // 1. Find the subscriber by the unsubscribe_token
      const { data: subscriber, error: selectError } = await supabase
        .from('email_subscribers')
        .select('email, unsubscribed, unsubscribe_token') // Ensure 'unsubscribe_token' column exists
        .eq('unsubscribe_token', token)
        .single();

      if (selectError && selectError.code !== 'PGRST116') { // PGRST116 = No rows found
         console.error('Supabase select error (unsubscribe):', selectError.message);
         status = 'error';
         message = 'An error occurred. Please try the link again or contact support.';
      } else if (!subscriber) {
         status = 'invalid';
         message = 'This unsubscribe link is invalid or has expired.';
      } else if (subscriber.unsubscribed) {
        status = 'already_unsubscribed';
        message = 'You have already been unsubscribed from our mailing list.';
      } else {
        // 2. Mark the user as unsubscribed
        const { error: updateError } = await supabase
          .from('email_subscribers')
          .update({
            unsubscribed: true,
            // Optional: You might also want to set `confirmed: false`
            // or clear the unsubscribe_token if it's single-use,
            // but for simplicity, we'll just mark as unsubscribed.
          })
          .eq('unsubscribe_token', token); // Ensure we update the correct record

        if (updateError) {
          console.error('Supabase update error (unsubscribe):', updateError.message);
          status = 'error';
          message = 'Failed to process your unsubscribe request. Please try again or contact support.';
        } else {
          status = 'success';
          message = "You have been successfully unsubscribed. We're sorry to see you go!";
        }
      }
    } catch (err: any) {
      console.error('Unsubscribe processing error:', err.message || err);
      status = 'error';
      message = 'An unexpected error occurred. Please try again later or contact support.';
    }
  }

  // --- UI Feedback Styling (Determined by status) ---
  const cardBgColor = status === 'success' ? 'bg-emerald-50 dark:bg-emerald-900/30'
                    : status === 'already_unsubscribed' ? 'bg-blue-50 dark:bg-blue-900/30'
                    : 'bg-red-50 dark:bg-red-900/30';
  const textColor = status === 'success' ? 'text-emerald-800 dark:text-emerald-200'
                   : status === 'already_unsubscribed' ? 'text-blue-800 dark:text-blue-200'
                   : 'text-red-800 dark:text-red-200';
  const headingColor = status === 'success' ? 'text-emerald-900 dark:text-emerald-100'
                      : status === 'already_unsubscribed' ? 'text-blue-900 dark:text-blue-100'
                      : 'text-red-900 dark:text-red-100';
  const headingText = status === 'success' ? 'Unsubscribed Successfully'
                     : status === 'already_unsubscribed' ? 'Already Unsubscribed'
                     : 'Unsubscribe Issue';

  return (
    <div className={`max-w-md w-full rounded-lg shadow-lg p-6 sm:p-8 ${cardBgColor}`}>
        <h1 className={`text-2xl font-semibold mb-4 text-center ${headingColor}`}>
            {headingText}
        </h1>
        <p className={`text-center mb-6 ${textColor}`}>
            {message}
        </p>
        <div className="text-center">
            <Link href="/" className="inline-block px-6 py-2 bg-slate-600 hover:bg-slate-700 text-white rounded font-semibold transition duration-200 focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2 dark:focus:ring-offset-neutral-950">
                Return to Homepage
            </Link>
        </div>
    </div>
  );
}


// --- Page Component (Default Export) ---
export default function UnsubscribePage({
  searchParams,
}: {
  searchParams?: { [key: string]: string | string[] | undefined };
}) {
  const token = typeof searchParams?.token === 'string' ? searchParams.token : undefined;

  // Check if Supabase env vars are available at the page level (optional check)
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL || !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY) {
    return (
      <div className="min-h-screen bg-[#F5F2EE] dark:bg-neutral-950 flex items-center justify-center px-4 py-12">
        <div className="max-w-md w-full rounded-lg shadow-lg p-6 sm:p-8 bg-red-50 dark:bg-red-900/30">
            <h1 className="text-2xl font-semibold mb-4 text-center text-red-900 dark:text-red-100">Configuration Error</h1>
            <p className="text-center text-red-800 dark:text-red-200">
                The application is not properly configured to handle unsubscriptions. Please contact support.
            </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F5F2EE] dark:bg-neutral-950 flex items-center justify-center px-4 py-12">
       <Suspense fallback={
           <div className="text-center text-neutral-600 dark:text-neutral-400">
                <p className="text-lg">Processing your unsubscribe request...</p>
           </div>
        }>
            <UnsubscribeHandler token={token} />
       </Suspense>
    </div>
  );
}