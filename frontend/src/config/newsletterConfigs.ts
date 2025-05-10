// src/config/newsletterConfigs.ts
export interface NewsletterConfig {
  slug: string
  type: 'neighbourhood' | 'tag' | 'other'
  title: string
  headline: string
  subheadline: string
  events: string[]
  primaryColor: string
  ctaText: string
  mode?: 'light' | 'dark'
  socialProof: string
  images?: {
    left: string
    right: string
  }
  useCustomComponent?: boolean
  accentBgClass: string
  accentTextClass: string
}

export const newsletterConfigs: NewsletterConfig[] = [
  /* ─────────── Existing configs ─────────── */
  {
    slug: 'east-london',
    type: 'neighbourhood',
    title: 'East London',
    headline: "East London's Vibrant Scene, All in One Place.",
    subheadline:
      'Get weekly updates on the coolest pop-ups, markets, gigs, and local happenings in East London. Curated, just for you.',
    events: ['East London'],
    primaryColor: 'blue',
    ctaText: 'Subscribe to East London Updates',
    mode: 'light',
    socialProof: 'Join thousands of East Londoners in the know.',
    images: { left: '/east-london-2.png', right: '/east-london-1.png' },
    accentBgClass: 'bg-blue-500',
    accentTextClass: 'text-blue-600',
  },
  /* ─────────── NEW: Hackney Wick ─────────── */
  {
    slug: 'hackney-wick',
    type: 'neighbourhood',
    title: 'Hackney Wick',
    headline: "Hackney Wick's Independent Spirit, All in One Place.",
    subheadline:
      'From canalside breweries to warehouse galleries, discover the most exciting goings-on in E9 every week.',
    events: ['Hackney Wick'],
    primaryColor: 'orange',
    ctaText: 'Subscribe to Hackney Wick Updates',
    mode: 'light',
    socialProof: 'Join fellow Wickers discovering the best on their doorstep.',
    images: { left: '/hackney-wick-1.png', right: '/hackney-wick-2.png' },
    accentBgClass: 'bg-orange-500',
    accentTextClass: 'text-orange-600',
  },
  /* ─────────── NEW: Bethnal Green ─────────── */
  {
    slug: 'bethnal-green',
    type: 'neighbourhood',
    title: 'Bethnal Green',
    headline: "Bethnal Green's Hidden Gems, Curated for You.",
    subheadline:
      'Art spaces, indie cinemas, late-night eateries, and local markets — served fresh to your inbox every Friday.',
    events: ['Bethnal Green'],
    primaryColor: 'teal',
    ctaText: 'Subscribe to Bethnal Green Updates',
    mode: 'light',
    socialProof: 'Be part of the growing Bethnal Green community in the know.',
    images: { left: '/bethnal-green-1.png', right: '/bethnal-green-2.png' },
    accentBgClass: 'bg-teal-500',
    accentTextClass: 'text-teal-600',
  },
  /* ─────────── NEW: Dalston ─────────── */
  {
    slug: 'dalston',
    type: 'neighbourhood',
    title: 'Dalston',
    headline: "Dalston’s Eclectic Scene, All in One Place.",
    subheadline:
      'Bars, live music, vintage fairs, and community gatherings — hand-picked for N16/N1 locals.',
    events: ['Dalston'],
    primaryColor: 'pink',
    ctaText: 'Subscribe to Dalston Updates',
    mode: 'light',
    socialProof: 'Join thousands of Dalstonites living life to the fullest.',
    images: { left: '/dalston-1.png', right: '/dalston-2.png' },
    accentBgClass: 'bg-pink-500',
    accentTextClass: 'text-pink-600',
  },
  /* ─────────── NEW: Hackney ─────────── */
  {
    slug: 'hackney',
    type: 'neighbourhood',
    title: 'Hackney',
    headline: "Hackney’s Best Events, Curated for You.",
    subheadline:
      'A weekly digest of food pop-ups, art openings, workshops, and more — across the borough.',
    events: ['Hackney'],
    primaryColor: 'emerald',
    ctaText: 'Subscribe to Hackney Updates',
    mode: 'light',
    socialProof: 'Join fellow Hackney locals who never miss a great event.',
    images: { left: '/hackney-wick-2.png', right: '/east-london-2.png' },
    accentBgClass: 'bg-emerald-500',
    accentTextClass: 'text-emerald-600',
  },
  /* ─────────── Existing configs (tags/other) ─────────── */
  {
    slug: 'art',
    type: 'tag',
    title: 'Art',
    headline: "London's Art Scene, Curated for You.",
    subheadline:
      'Your weekly guide to the most exciting exhibitions, openings, and art events near you. Free forever.',
    events: ['Art'],
    primaryColor: 'red',
    ctaText: 'Subscribe to Art Updates',
    mode: 'light',
    socialProof: "Join fellow art lovers enjoying London's culture.",
    images: { left: '/london-art-2.png', right: '/london-art-1.png' },
    accentBgClass: 'bg-rose-500',
    accentTextClass: 'text-rose-600',
  },
  {
    slug: 'pride',
    type: 'tag',
    title: 'LGBTQ+',
    headline: 'London’s LGBTQ+ Scene, Curated for You.',
    subheadline:
      'Weekly picks of the best queer parties, talks, art, and community events. Always free.',
    events: ['LGBTQ+'],
    primaryColor: 'purple',
    ctaText: 'Subscribe to LGBTQ+ Updates',
    mode: 'light',
    socialProof: 'Join fellow queer Londoners in the know.',
    images: { left: '/london-pride-1.png', right: '/london-pride-2.png' },
    useCustomComponent: true,
    accentBgClass: 'bg-purple-500',
    accentTextClass: 'text-purple-600',
  },
  {
    slug: 'markets',
    type: 'tag',
    title: 'Markets',
    headline: 'London’s Best Markets, Curated for You.',
    subheadline:
      'Find the best pop-ups, street food, vintage stalls, and more — weekly and free.',
    events: ['Markets'],
    primaryColor: 'green',
    ctaText: 'Subscribe to Market Updates',
    mode: 'light',
    socialProof: 'Join fellow market-lovers who never miss a hidden gem.',
    images: { left: '/london-markets-1.png', right: '/london-markets-2.png' },
    accentBgClass: 'bg-green-500',
    accentTextClass: 'text-green-600',
  },
]
