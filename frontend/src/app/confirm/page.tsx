import { createClient } from '@supabase/supabase-js';
import Link from 'next/link';
import { Suspense } from 'react';


const supabase = createClient(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_KEY!
);

// Define the props type for the Page component, including searchParams
interface ConfirmPageProps {
  searchParams: { email?: string; token?: string };
}

// --- Core Confirmation Logic Component ---
// This async component performs the actual check against Supabase
async function ConfirmationHandler({ email, token }: { email?: string; token?: string }) {
  // Define possible states for user feedback
  let status: 'success' | 'error' | 'invalid' | 'already_confirmed' = 'invalid';
  let message: string = 'Invalid confirmation link provided.';

  // Only proceed if both email and token are present in the URL
  if (email && token) {
    try {
      // 1. Look for a subscriber matching the email and the specific confirmation token.
      const { data: subscriber, error: selectError } = await supabase
        .from('email_subscribers')
        .select('confirmed, confirm_token')
        .eq('email', email)
        .eq('confirm_token', token)
        .single();

      // Handle potential errors during the database query
      if (selectError && selectError.code !== 'PGRST116') { // PGRST116 = "No rows found", handled below
         console.error('Supabase select error:', selectError.message);
         status = 'error';
         message = 'An error occurred while verifying your email. Please try again later.';
      }
      // Case 1: No record found matching email AND token
      else if (!subscriber) {
          // Check if the email exists but is ALREADY confirmed (maybe link clicked before, or different token was used)
          const { data: alreadyConfirmedSubscriber, error: checkError } = await supabase
            .from('email_subscribers')
            .select('email') // We just need to know if a row exists
            .eq('email', email)
            .eq('confirmed', true) // Check if confirmation flag is true
            .maybeSingle(); // Allows 0 or 1 row

          if (checkError) {
              console.error('Supabase check (already confirmed) error:', checkError.message);
              status = 'error';
              message = 'An error occurred while checking your status. Please try again later.';
          } else if (alreadyConfirmedSubscriber) {
              // Email exists and is confirmed -> Treat as "Already Confirmed"
              status = 'already_confirmed';
              message = 'This email address has already been confirmed.';
          } else {
              // No matching token, and not already confirmed -> Link is invalid or expired
              status = 'invalid';
              message = 'This confirmation link is invalid or has expired.';
          }
      }
      // Case 2: Record found, but the 'confirmed' flag is already true
      else if (subscriber.confirmed) {
        status = 'already_confirmed';
        message = 'Your email address has already been confirmed.';
      }
      // Case 3: Record found, token matches, and not yet confirmed -> Success path!
      else {
        // Update the subscriber record: set confirmed = true, clear the token
        const { error: updateError } = await supabase
          .from('email_subscribers')
          .update({
              confirmed: true,        // Mark as confirmed
              confirm_token: null     // Clear the token so link cannot be reused
           })
          .eq('email', email); // Use the email (Primary Key) to identify the row

        // Handle potential errors during the update operation
        if (updateError) {
          console.error('Supabase update error:', updateError.message);
          status = 'error';
          message = 'Failed to confirm your email. Please try clicking the link again or contact support.';
        } else {
          // Update was successful!
          status = 'success';
          message = 'Success! Your email address has been confirmed. Welcome aboard!';
        }
      }
    } catch (err: any) { // Catch any unexpected errors during the process
      console.error('Confirmation processing error:', err.message || err);
      status = 'error';
      message = 'An unexpected error occurred. Please try again later or contact support.';
    }
  } // End if (email && token)

  // --- UI Feedback Styling ---
  // Determine colors and text based on the final status
  const cardBgColor = status === 'success' ? 'bg-emerald-50 dark:bg-emerald-900/30'
                    : status === 'already_confirmed' ? 'bg-blue-50 dark:bg-blue-900/30'
                    : 'bg-red-50 dark:bg-red-900/30'; // invalid or error
  const textColor = status === 'success' ? 'text-emerald-800 dark:text-emerald-200'
                   : status === 'already_confirmed' ? 'text-blue-800 dark:text-blue-200'
                   : 'text-red-800 dark:text-red-200';
  const headingColor = status === 'success' ? 'text-emerald-900 dark:text-emerald-100'
                      : status === 'already_confirmed' ? 'text-blue-900 dark:text-blue-100'
                      : 'text-red-900 dark:text-red-100';
  const headingText = status === 'success' ? 'Confirmation Successful'
                     : status === 'already_confirmed' ? 'Already Confirmed'
                     : 'Confirmation Issue'; // invalid or error

  // --- Return the UI Card ---
  return (
    <div className={`max-w-md w-full rounded-lg shadow-lg p-6 sm:p-8 ${cardBgColor}`}>
        <h1 className={`text-2xl font-semibold mb-4 text-center ${headingColor}`}>
            {headingText}
        </h1>
        <p className={`text-center mb-6 ${textColor}`}>
            {message}
        </p>
        {/* Always show a link back to the homepage */}
        <div className="text-center">
            <Link href="/" className="inline-block px-6 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded font-semibold transition duration-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 dark:focus:ring-offset-neutral-950">
                Return to Homepage
            </Link>
        </div>
    </div>
  );
}


// --- Page Component (Default Export) ---
// This wraps the async logic component in Suspense for a loading state.
export default function ConfirmPage({ searchParams }: ConfirmPageProps) {
  return (
    // Basic page layout - centers the confirmation card
    <div className="min-h-screen bg-[#F5F2EE] dark:bg-neutral-950 flex items-center justify-center px-4 py-12">
       {/* Suspense provides a fallback UI while the async ConfirmationHandler runs */}
       <Suspense fallback={
           <div className="text-center text-neutral-600 dark:text-neutral-400">
                <p className="text-lg">Verifying your confirmation...</p>
                {/* You could add a simple loading spinner SVG here */}
           </div>
        }>
            {/* Pass the searchParams down to the handler component */}
            <ConfirmationHandler email={searchParams.email} token={searchParams.token} />
       </Suspense>
    </div>
  );
}
