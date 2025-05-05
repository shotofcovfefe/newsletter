import { createClient } from '@supabase/supabase-js';
import Link from 'next/link';
import { Suspense } from 'react';

// Initialize Supabase client (ensure these env vars are available server-side)
const supabase = createClient(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_KEY!
);

// Define the props type expected by the ConfirmationHandler component
interface ConfirmationHandlerProps {
    email?: string;
    token?: string;
}

// --- Core Confirmation Logic Component ---
// This async component performs the actual check against Supabase
// Use the specific props interface defined above
async function ConfirmationHandler({ email, token }: ConfirmationHandlerProps) {
  let status: 'success' | 'error' | 'invalid' | 'already_confirmed' = 'invalid';
  let message: string = 'Invalid confirmation link provided.'; // Default message

  if (email && token) {
    try {
      // 1. Find the subscriber by email and token
      const { data: subscriber, error: selectError } = await supabase
        .from('email_subscribers')
        .select('confirmed, confirm_token') // Select only needed fields that exist
        .eq('email', email)                 // Match the email from the URL
        .eq('confirm_token', token)         // Match the token from the URL
        .single(); // Expects 0 or 1 matching row

      if (selectError && selectError.code !== 'PGRST116') { // PGRST116 = No rows found
         console.error('Supabase select error:', selectError.message);
         status = 'error';
         message = 'An error occurred while verifying your email. Please try again later.';
      }
      else if (!subscriber) {
         const { data: alreadyConfirmedSubscriber, error: checkError } = await supabase
          .from('email_subscribers')
          .select('email')
          .eq('email', email)
          .eq('confirmed', true)
          .maybeSingle();

          if (checkError) {
              console.error('Supabase check (already confirmed) error:', checkError.message);
              status = 'error';
              message = 'An error occurred while checking your status. Please try again later.';
          } else if (alreadyConfirmedSubscriber) {
              status = 'already_confirmed';
              message = 'This email address has already been confirmed.';
          } else {
              status = 'invalid';
              message = 'This confirmation link is invalid or has expired.';
          }
      }
      else if (subscriber.confirmed) {
        status = 'already_confirmed';
        message = 'Your email address has already been confirmed.';
      }
      else {
        const { error: updateError } = await supabase
          .from('email_subscribers')
          .update({ confirmed: true, confirm_token: null })
          .eq('email', email); // Use the email (Primary Key)

        if (updateError) {
          console.error('Supabase update error:', updateError.message);
          status = 'error';
          message = 'Failed to confirm your email. Please try clicking the link again or contact support.';
        } else {
          status = 'success';
          message = 'Success! Your email address has been confirmed. Welcome aboard!';
        }
      }
    } catch (err: any) {
      console.error('Confirmation processing error:', err.message || err);
      status = 'error';
      message = 'An unexpected error occurred. Please try again later or contact support.';
    }
  }

  // --- UI Feedback Styling (Determined by status) ---
  const cardBgColor = status === 'success' ? 'bg-emerald-50 dark:bg-emerald-900/30'
                    : status === 'already_confirmed' ? 'bg-blue-50 dark:bg-blue-900/30'
                    : 'bg-red-50 dark:bg-red-900/30';
  const textColor = status === 'success' ? 'text-emerald-800 dark:text-emerald-200'
                   : status === 'already_confirmed' ? 'text-blue-800 dark:text-blue-200'
                   : 'text-red-800 dark:text-red-200';
  const headingColor = status === 'success' ? 'text-emerald-900 dark:text-emerald-100'
                      : status === 'already_confirmed' ? 'text-blue-900 dark:text-blue-100'
                      : 'text-red-900 dark:text-red-100';
  const headingText = status === 'success' ? 'Confirmation Successful'
                     : status === 'already_confirmed' ? 'Already Confirmed'
                     : 'Confirmation Issue';

  // --- Return the UI Card ---
  return (
    <div className={`max-w-md w-full rounded-lg shadow-lg p-6 sm:p-8 ${cardBgColor}`}>
        <h1 className={`text-2xl font-semibold mb-4 text-center ${headingColor}`}>
            {headingText}
        </h1>
        <p className={`text-center mb-6 ${textColor}`}>
            {message}
        </p>
        <div className="text-center">
            <Link href="/" className="inline-block px-6 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded font-semibold transition duration-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 dark:focus:ring-offset-neutral-950">
                Return to Homepage
            </Link>
        </div>
    </div>
  );
}


// --- Page Component (Default Export) ---
// Removed the custom ConfirmPageProps interface and typed props inline
export default function ConfirmPage({
  searchParams,
}: {
  // Use the standard Next.js type for searchParams in App Router Server Components
  searchParams?: { [key: string]: string | string[] | undefined };
}) {
  // Safely extract email and token, as searchParams can contain strings, arrays, or be undefined
  const email = typeof searchParams?.email === 'string' ? searchParams.email : undefined;
  const token = typeof searchParams?.token === 'string' ? searchParams.token : undefined;

  return (
    // Basic page layout - centers the confirmation card
    <div className="min-h-screen bg-[#F5F2EE] dark:bg-neutral-950 flex items-center justify-center px-4 py-12">
       {/* Suspense provides a fallback while the async ConfirmationHandler runs */}
       <Suspense fallback={
           <div className="text-center text-neutral-600 dark:text-neutral-400">
                <p className="text-lg">Verifying your confirmation...</p>
           </div>
        }>
            {/* Pass the potentially undefined email/token */}
            <ConfirmationHandler email={email} token={token} />
       </Suspense>
    </div>
  );
}