// Add "use client" directive as the VERY FIRST LINE for App Router
"use client";

import { useState } from 'react';
// import type { NextPage } from 'next'; // Type annotation might vary depending on exact setup

// --- Confetti Piece Component ---
// Can be defined here or moved to a separate components file
function ConfettiPiece({ styles }: { styles: React.CSSProperties }) {
  // Applies the keyframes defined in styles/globals.css
  return <div className="absolute w-[4px] h-[8px] animate-[tiny-confetti-bang_600ms_ease-out_forwards]" style={styles}></div>;
}

// --- Constants ---
const interestTags = [
  'Art', 'Food & Drink', 'Live Music', 'Workshops',
  'Comedy', 'Markets', 'Families', 'Date Night', 'Solo Friendly'
];
const confettiColors = [
  'bg-pink-500', 'bg-yellow-500', 'bg-green-500',
  'bg-blue-500', 'bg-indigo-500', 'bg-purple-500', 'bg-red-500'
];

export default function Home() {
  // --- State ---
  const [checkedInterests, setCheckedInterests] = useState<Record<string, boolean>>({});
  const [burstingTag, setBurstingTag] = useState<string | null>(null);

  // --- Handler ---
  const handleInterestChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { value, checked } = event.target;
    setCheckedInterests(prev => ({ ...prev, [value]: checked }));
    if (checked) {
      setBurstingTag(value);
      setTimeout(() => { setBurstingTag(null); }, 600); // Reset after animation
    }
  };

  return (
    <main className="bg-[#F5F2EE] text-black dark:bg-[#0A0A0A] dark:text-white min-h-screen flex flex-col justify-between">
      {/* Metadata is typically handled via export const metadata = {...} in app router */}

      {/* Hero section */}
      <section className="flex-1 flex items-center justify-center px-6 py-32">
        <div className="w-full text-center space-y-10">
          <h1 className="text-5xl sm:text-6xl font-serif font-semibold leading-tight max-w-3xl mx-auto">
            Local London events you'll actually <i>want</i> to go to.
          </h1>
          <p className="text-lg sm:text-xl text-neutral-400 leading-relaxed mt-4 max-w-xl mx-auto">
            Every Friday, we send you five handpicked events that match your postcode and passions.
            No noise. No scrolling. Just better weekends.
          </p>

          <form
            action="YOUR_FORM_ACTION_URL_OR_ENDPOINT" // <-- Replace this
            method="POST"
            // target="hidden_iframe" // Only needed for hidden iframe Google Form submission
            // onsubmit="submitted=true;" // Only needed for hidden iframe Google Form submission
            className="bg-white dark:bg-neutral-900 shadow-md rounded-xl px-6 py-8 space-y-6 text-left max-w-xl mx-auto"
          >
            <div className="flex flex-col sm:flex-row gap-4">
              <input
                type="email"
                name="ENTRY_ID_FOR_EMAIL" // <-- Use correct name/entry ID
                placeholder="Your email address"
                required
                className="flex-1 p-3 border border-neutral-300 dark:border-neutral-700 rounded focus:outline-none focus:ring-4 focus:ring-black/20 dark:bg-neutral-800 dark:text-white"
              />
              <input
                type="text"
                name="ENTRY_ID_FOR_POSTCODE" // <-- Use correct name/entry ID
                placeholder="Postcode"
                required
                className="p-3 border border-neutral-300 dark:border-neutral-700 rounded focus:outline-none focus:ring-4 focus:ring-black/20 dark:bg-neutral-800 dark:text-white sm:w-40"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-400">
                What are you into?
              </label>
              <div className="flex flex-wrap gap-2">
                {interestTags.map((tag) => (
                  <div key={tag} className="relative"> {/* Relative container for confetti */}
                    <label className="cursor-pointer">
                      <input
                        type="checkbox"
                        name="ENTRY_ID_FOR_INTERESTS" // <-- Use correct name/entry ID
                        value={tag}
                        className="hidden peer"
                        onChange={handleInterestChange} // Attach handler
                        checked={!!checkedInterests[tag]} // Control state
                      />
                      <span className="
                        relative /* Needed if using ::after for checkmark instead */
                        inline-block px-3 py-1 border border-neutral-300 dark:border-neutral-600
                        rounded-full text-sm transition-colors duration-150 ease-in-out
                        peer-checked:bg-black peer-checked:text-white
                        dark:peer-checked:bg-white dark:peer-checked:text-black
                        hover:border-neutral-500 dark:hover:border-neutral-400
                        active:scale-95
                      ">
                        {tag}
                      </span>
                    </label>

                    {/* Conditionally render confetti */}
                    {burstingTag === tag && (
                          Array.from({ length: 30 }).map((_, i) => {
                            // random trajectory
                            const angle = Math.random() * 360;
                            const distance = 60 + Math.random() * 40;   // 60-100 px
                            const dx = Math.cos(angle) * distance;
                            const dy = Math.sin(angle) * distance;

                            // random piece styling
                            const size = 3 + Math.random() * 3;          // 3-6 px
                            const delay = Math.random() * 0.15;          // slight stagger
                            const color = confettiColors[Math.floor(Math.random() * confettiColors.length)];

                            return (
                              <div
                                key={i}
                                style={{
                                  '--dx': `${dx}px`,
                                  '--dy': `${dy}px`,
                                  '--angle': `${Math.random() * 360}deg`,
                                  left: '50%',
                                  top : '40%',
                                  width : `${size}px`,
                                  height: `${size * 2}px`,
                                  animationDelay: `${delay}s`,
                                } as React.CSSProperties}
                                className={`absolute pointer-events-none animate-[tiny-confetti-pop_1s_ease-out_forwards] ${color}`}
                              />
                            );
                          })
                        )}
                  </div>
                ))}
              </div>
            </div>

            <button
              type="submit"
              className="w-full bg-black text-white dark:bg-white dark:text-black py-3 rounded text-base font-medium hover:opacity-90 transition"
            >
              Subscribe
            </button>
          </form>

          <p className="text-sm text-neutral-500 dark:text-neutral-400 max-w-xl mx-auto">
            Join 5,000+ Londoners finding better weekends.
          </p>
        </div>
      </section>

      <footer className="w-full text-center text-xs text-neutral-500 dark:text-neutral-400 pb-6">
        Built with ❤️ in London. No tracking. No ads. Ever.
      </footer>

      {/* Only include iframe/script if using hidden iframe method for Google Forms */}
      {/* <iframe name="hidden_iframe" id="hidden_iframe" style={{ display: 'none' }} ></iframe> */}
      {/* <script dangerouslySetInnerHTML={{ __html: `var submitted=false;` }} /> */}

    </main>
  )
}