import Image from 'next/image'
import Link from 'next/link' // Keep Link import

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-[#F5F2EE] dark:bg-neutral-950 text-neutral-900 dark:text-neutral-100">

      {/* Hero image and headline */}
      <section className="relative w-full h-[300px] sm:h-[400px] overflow-hidden">
        <Image
          src="/london-events-1.png"
          alt="People enjoying diverse events in London"
          fill
          className="object-cover"
          priority
        />
        <div className="absolute inset-0 bg-black/30"></div> {/* Optional: Subtle overlay */}
        <div className="absolute inset-0 flex items-center justify-center px-6 text-center">
          <h1 className="text-white text-4xl sm:text-5xl lg:text-6xl font-serif font-semibold leading-tight drop-shadow-md">
            Discover events in London<br className="hidden sm:inline" /> that actually matter to you
          </h1>
        </div>
      </section>

      {/* Main Content Area */}
      <section className="max-w-3xl mx-auto px-6 py-16 sm:py-20 space-y-12">

        {/* Intro Paragraph */}
        <div className="text-center">
          <p className="text-xl text-neutral-700 dark:text-neutral-300 leading-relaxed max-w-2xl mx-auto">
            Unfog London is your no-scroll, no-noise newsletter for London events. Tell us what you like — and your postcode —
            and we'll do the curating. Every Friday, get five events handpicked for your tastes and area.
          </p>
        </div>

        {/* Overview Section */}
        <div>
          <h2 className="text-3xl font-semibold font-serif mb-4 text-neutral-900 dark:text-neutral-100">Overview</h2>
          <div className="prose prose-neutral dark:prose-invert prose-lg max-w-none space-y-4">
            <p>
              Tired of endless scrolling through generic listings to find events you actually care about in London? So were we.
            </p>
            <p>
              Unfog London cuts through the noise. We deliver a curated list of interesting and relevant happenings
              across the city, tailored directly to your tastes and your local area.
            </p>
            <p>
              Sign up, tell us what kind of events you love (from art exhibitions and live music to family workshops
              and foodie pop-ups) and your London postcode. We'll do the rest, sending you a simple, personalized
              email digest <strong className="font-medium">every Friday</strong> featuring events near you that match your interests.
            </p>
            <p>
              Spend less time searching, more time experiencing the best of London.
            </p>
          </div>
        </div>

        {/* Event Sourcing Section */}
        <div>
            <h2 className="text-3xl font-semibold font-serif mb-4 text-neutral-900 dark:text-neutral-100 pt-6">How We Find Events</h2>
            <div className="prose prose-neutral dark:prose-invert prose-lg max-w-none space-y-4">
                <p>
                    We focus on uncovering unique and local happenings often missed by the big platforms. Our process combines human curation with technology.
                </p>
                <p>
                    An AI-driven pipeline continuously scrapes and analyzes information from hundreds of sources, including hyperlocal newsletters, community forums, direct venue listings, and social media groups across London. This allows us to surface events that don't typically appear on mainstream sites like Time Out or Eventbrite until much later, if at all.
                </p>
                <p>
                    Our team then verifies and selects the most relevant and interesting events, ensuring they align with your preferences before they land in your inbox.
                </p>
            </div>
        </div>
      </section> {/* End of main content section */}

      {/* FAQ Section */}
      {/* pb-24 on this section provides the main gap before the global page footer */}
      <section className="max-w-3xl mx-auto px-6 pb-24 space-y-12 pt-0"> {/* Ensure no excessive top padding if it's distinct from above section */}
        <h2 className="text-3xl font-semibold font-serif text-neutral-900 dark:text-neutral-100">Frequently Asked Questions</h2>
        <dl className="space-y-8 divide-y divide-neutral-200 dark:divide-neutral-700">
          {[
             {
              q: 'What kind of events do you feature?',
              a: "The newsletter covers a wide range — music, art, film, comedy, workshops, food, family, free happenings, markets, and more. If it's interesting and happening in London, we aim to find it.",
            },
            {
              q: 'How often will I receive the newsletter?',
              a: 'Every Friday morning, giving you time to plan your weekend.',
            },
            {
              q: 'Where do you source events from?',
              a: "The pipeline uses a mix of AI scraping (local newsletters, venue sites, community boards) and human curation to find unique events often missed by larger platforms. See 'How We Find Events' above for more detail.",
            },
            {
              q: 'How does the personalization work?',
              a: "You provide your London postcode and select interest categories. Our system matches you with nearby events relevant to those interests.",
            },
            {
              q: 'Is this service free?',
              a: 'Yes, Unfog London is completely free for subscribers.',
            },
            {
              q: 'Why do you need my postcode?',
              a: 'To find local events, We need a pinhead around which to draw a hard radius to search. If you\'re concerned about privacy, simply give a local postcode instead.',
            },
            {
              q: 'Can I update my postcode or preferences?',
              a: 'Yes. You can resubmit the signup form with your updated details using the same email address, and we will update your profile.',
            },
            {
              q: 'How do I unsubscribe?',
              a: "There's an unsubscribe link at the bottom of every email we send.",
            },
            {
              q: 'Who runs this?',
              a: 'Unfog London was founded and is run by me, Andy. I\'m a developer and East London local, and simply wanted a better way to discover local events.',
            },
            {
              q: 'How can I support?',
              a: 'If you enjoy this newsletter, you can <a href="https://buymeacoffee.com/unfog.london" target="_blank" rel="noopener noreferrer" class="text-emerald-600 dark:text-emerald-400 hover:underline font-medium">☕️ buy me a coffee ☕️</a> to help support my work!',
            },
            {
              q: 'How can I submit an event?',
              a: 'While we primarily rely on our discovery process, you can reach out via the contact details possibly listed in the footer. We only include events that fit our curated criteria.',
            },
            {
              q: 'What parts of London do you cover?',
              a: 'We aim to cover events across all London boroughs.',
            },
            {
              q: 'Does it work equally well everywhere?',
              a: 'It works best in East London, but we are expanding!',
            },
          ].map(({ q, a }, i) => (
            // --- ADDED pb-4 for spacing below each FAQ item's text ---
            <div key={i} className="pt-8 pb-4 first:pt-0">
              <dt className="font-serif text-lg font-semibold text-neutral-900 dark:text-neutral-100">{q}</dt>
              {/* Using dangerouslySetInnerHTML to render the link in "Who runs this?" */}
              <dd className="mt-2 text-neutral-700 dark:text-neutral-300 leading-relaxed" dangerouslySetInnerHTML={{ __html: a.replace(/\n/g, '<br />') }}></dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  )
}