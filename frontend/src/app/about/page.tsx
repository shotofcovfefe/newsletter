import Image from 'next/image'

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-[#F5F2EE] text-neutral-900">
      {/* Hero image and headline */}
      <section className="relative w-full h-[300px] sm:h-[400px] overflow-hidden">
        <Image
          src="/london-events-1.png"
          alt="People at a London event"
          layout="fill"
          objectFit="cover"
          className="brightness-[0.65]"
          priority
        />
        <div className="absolute inset-0 flex items-center justify-center px-6">
          <h1 className="text-white text-4xl sm:text-5xl lg:text-6xl font-serif font-semibold text-center leading-tight">
            Discover events in London<br />that actually matter to you
          </h1>
        </div>
      </section>

      {/* Intro + Overview */}
      <section className="max-w-3xl mx-auto px-6 py-20 space-y-12">
        <div className="text-center space-y-4">
          <p className="text-xl text-neutral-700 leading-relaxed max-w-2xl mx-auto">
            Niche London Events is a no-scroll, no-noise newsletter. Tell us what you like — and where you live —
            and we’ll do the curating. Every Friday, get five events handpicked for your tastes and area.
          </p>
        </div>

        <div>
          <h2 className="text-2xl font-semibold mb-4">Overview</h2>
          <div className="prose prose-neutral prose-lg max-w-none">
            <p>
              Tired of endless scrolling to find events you actually care about in London? So were we.
            </p>
            <p>
              Niche London Events cuts through the noise. We deliver a curated list of interesting and relevant happenings
              across the city, tailored directly to your tastes and your local area.
            </p>
            <p>
              Sign up, tell us what kind of events you love (from art exhibitions and live music to family workshops
              and foodie pop-ups) and your London postcode. We'll do the rest, sending you a simple, personalized
              email digest <em>[Specify Frequency, e.g., weekly, every Friday]</em> featuring events near you that match your interests.
            </p>
            <p>
              Spend less time searching, more time experiencing London.
            </p>
          </div>
        </div>
      </section>
      <section className="max-w-3xl mx-auto px-6 pb-24 space-y-12">
  <h2 className="text-2xl font-semibold">Frequently Asked Questions</h2>
  <dl className="space-y-10 divide-y divide-neutral-200">
    {[
      {
        q: 'What kind of events do you feature?',
        a: 'We cover a wide range — music, art, film, comedy, workshops, food, family, free happenings, and more. If it’s interesting and local, we’ll find it.',
      },
      {
        q: 'How often will I receive the newsletter?',
        a: 'Every Friday morning, so you’ve got time to plan your weekend.',
      },
      {
        q: 'How do you find the events?',
        a: 'We monitor venue listings, community boards, and tips from our readers — then filter and select based on your location and interests.',
      },
      {
        q: 'How does the personalization work?',
        a: 'You give us your London postcode and select categories. We do the rest — matching you with nearby events you’re likely to love.',
      },
      {
        q: 'Is this service free?',
        a: 'Yes. Totally free.',
      },
      {
        q: 'Can I update my postcode or preferences?',
        a: 'Yup! Just reply to any email or re-submit the form with new details.',
      },
      {
        q: 'How do I unsubscribe?',
        a: 'There’s an unsubscribe link at the bottom of every email.',
      },
      {
        q: 'Who runs this?',
        a: 'A tired Londoner who didn’t want to miss good stuff anymore.',
      },
      {
        q: 'How can I submit an event?',
        a: 'Send us an email. We only include events if they’re genuinely interesting.',
      },
      {
        q: 'What parts of London do you cover?',
        a: 'All of it.',
      },
    ].map(({ q, a }, i) => (
      <div key={i} className="pt-8 first:pt-0">
        <dt className="font-serif text-lg font-semibold text-neutral-900">{q}</dt>
        <dd className="mt-2 text-neutral-700 leading-relaxed">{a}</dd>
      </div>
    ))}
  </dl>
</section>
    </div>
  )
}
