// src/config/newsletterConfigs.ts

export interface NewsletterConfig {
  slug: string;
  type: 'neighbourhood' | 'tag' | 'other';
  title: string;
  headline: string;
  subheadline: string;
  events: string[]; // For querying or metadata, not hardcoded event display
  primaryColor: string; // e.g., 'blue', 'orange' - general theme hint
  ctaText: string;
  mode?: 'light' | 'dark'; // Base mode for the page/components
  socialProof: string;
  images?: {
    left: string;
    right: string;
  };
  useCustomComponent?: boolean;
  accentBgClass: string;     // e.g., 'bg-blue-500'
  accentTextClass: string;   // e.g., 'text-blue-600'
  showFogOverlay?: boolean;

  // Granular theme object for detailed styling
  theme?: {
    mode: 'light' | 'dark'; // Derived from existing 'mode'
    accentColor?: string;   // Tailwind text color class, derived from 'accentTextClass' for consistency

    mainTextColor?: string;
    heroHeadlineColor?: string;
    heroSubheadlineColor?: string;

    signupContainerBg?: string;
    socialProofColor?: string;

    // Properties for EventPreviewCard (main interactive grid cards)
    cardBackgroundColor?: string;
    cardBorderColor?: string;
    cardTitleColor?: string;        // Also used as a base for FloatingEventBackgroundCard title
    cardSubtitleColor?: string;
    cardDateLineColor?: string;     // Typically uses accentColor
    cardBlurbColor?: string;
    cardVibesColor?: string;

    // Specific for FloatingEventBackgroundCard (decorative background cards)
    cardFloatingTitleOverlayBg?: string; // NEW: Background for the title overlay on floating cards

    // Corner image opacity
    cornerImageOpacity?: string;
  };
}

// Helper function to generate a default theme based on existing config values
const generateThemeFromConfig = (cfg: Omit<NewsletterConfig, 'theme'>): Required<NonNullable<NewsletterConfig['theme']>> => {
  const isDark = cfg.mode === 'dark';

  // Base theme, defaults to light mode values
  const theme: Required<NonNullable<NewsletterConfig['theme']>> = {
    mode: cfg.mode || 'light',
    accentColor: cfg.accentTextClass, // Use existing accentTextClass for primary accent

    mainTextColor: isDark ? 'text-neutral-200' : 'text-neutral-800',
    heroHeadlineColor: isDark ? 'text-neutral-100' : 'text-neutral-900',
    heroSubheadlineColor: isDark ? 'text-neutral-300' : 'text-neutral-600',

    signupContainerBg: isDark ? 'bg-neutral-800/70' : 'bg-white/70',
    socialProofColor: isDark ? 'text-neutral-400' : 'text-neutral-500',

    // Defaults for EventPreviewCard (main grid)
    cardBackgroundColor: isDark ? 'bg-neutral-800' : 'bg-white',
    cardBorderColor: isDark ? 'border-neutral-700' : 'border-neutral-200',
    cardTitleColor: isDark ? 'text-neutral-100' : 'text-neutral-800', // General title color
    cardSubtitleColor: isDark ? 'text-neutral-400' : 'text-neutral-600',
    cardDateLineColor: cfg.accentTextClass, // Use main accent for date lines in grid cards
    cardBlurbColor: isDark ? 'text-neutral-400' : 'text-neutral-600',
    cardVibesColor: isDark ? 'text-sky-400' : 'text-sky-600',

    // Default for FloatingEventBackgroundCard title overlay background
    cardFloatingTitleOverlayBg: isDark ? 'bg-black/60' : 'bg-white/70',

    cornerImageOpacity: isDark ? 'opacity-30' : 'opacity-50'
  };

  return theme;
};


export const newsletterConfigs: NewsletterConfig[] = ([
  {
    slug: 'east-london',
    type: 'neighbourhood',
    title: 'East London',
    headline: "East London's Vibrant Scene, All in One Place.",
    subheadline:
      'Get weekly updates on the coolest pop-ups, markets, gigs, and local happenings in East London. Curated, just for you.',
    events: ['Hackney', 'Bethnal Green', 'Dalston', 'London Fields', 'Hackney Wick','Tower Hamlets'],
    primaryColor: 'blue',
    ctaText: 'Subscribe to East London Updates',
    mode: 'light',
    socialProof: 'Join thousands of East Londoners in the know.',
    images: { left: '/east-london-2.png', right: '/east-london-1.png' },
    accentBgClass: 'bg-blue-500',
    accentTextClass: 'text-blue-600',
    showFogOverlay: false,
  },
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
    showFogOverlay: false,
  },
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
    showFogOverlay: false,
  },
  {
    slug: 'dalston',
    type: 'neighbourhood',
    title: 'Dalston',
    headline: "Dalston's Eclectic Scene, All in One Place.",
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
    showFogOverlay: false,
  },
  {
    slug: 'london-fields',
    type: 'neighbourhood',
    title: 'London Fields',
    headline: "London Fields' Local Gems, Curated for You.",
    subheadline:
      'Park events, breweries, cafés, and weekend markets — the best of E8 delivered to your inbox.',
    events: ['London Fields'],
    primaryColor: 'green',
    ctaText: 'Subscribe to London Fields Updates',
    mode: 'light',
    socialProof: "Join locals who never miss what's happening in London Fields.",
    images: { left: '/london-fields-1.png', right: '/london-fields-2.png' }, // Placeholder images
    accentBgClass: 'bg-green-500',
    accentTextClass: 'text-green-600',
    showFogOverlay: false,
  },
    {
    slug: 'tower-hamlets',
    type: 'neighbourhood',
    title: 'Tower Hamlets',
    headline: "Discover Tower Hamlets: Events & Local Life.",
    subheadline:
      "Your weekly guide to what's happening across Tower Hamlets, from riverside walks to vibrant markets and community festivals.",
    events: ['Tower Hamlets'],
    primaryColor: 'yellow',
    ctaText: 'Get Tower Hamlets Updates',
    mode: 'light',
    socialProof: 'Stay connected with your Tower Hamlets community.',
    images: { left: '/tower-hamlets-1.png', right: '/tower-hamlets-2.png' },
    accentBgClass: 'bg-yellow-500',
    accentTextClass: 'text-yellow-600',
    showFogOverlay: false,
  },
  {
    slug: 'hackney',
    type: 'neighbourhood',
    title: 'Hackney',
    headline: "Hackney's Best Events, Curated for You.",
    subheadline:
      'A weekly digest of food pop-ups, art openings, workshops, and more — across the borough.',
    events: ['Hackney'],
    primaryColor: 'emerald',
    ctaText: 'Subscribe to Hackney Updates',
    mode: 'dark',
    socialProof: 'Join fellow Hackney locals who never miss a great event.',
    images: { left: '/hackney-wick-2.png', right: '/east-london-2.png' },
    accentBgClass: 'bg-emerald-500',
    accentTextClass: 'text-emerald-600',
    showFogOverlay: true,
  },
  {
    slug: 'art',
    type: 'tag',
    title: 'Art',
    headline: "London's Art Scene, Curated for You.",
    subheadline:
      'Your weekly guide to the most exciting exhibitions, openings, and art events near you. Free forever.',
    events: ['art', 'art_lovers', 'artistic', 'creatives', 'art_and_exhibitions'],
    primaryColor: 'red',
    ctaText: 'Subscribe to Art Updates',
    mode: 'light',
    socialProof: "Join fellow art lovers enjoying London's culture.",
    images: { left: '/london-art-2.png', right: '/london-art-1.png' },
    accentBgClass: 'bg-rose-500',
    accentTextClass: 'text-rose-600',
    showFogOverlay: false,
  },
  {
    slug: 'pride',
    type: 'tag',
    title: 'LGBTQ+',
    headline: "London's LGBTQ+ Scene, Curated for You.",
    subheadline:
      'Weekly picks of the best queer parties, talks, art, and community events. Always free.',
    events: ['lgbtq+', 'lgbtq', 'queer', 'pride', 'drag'],
    primaryColor: 'purple',
    ctaText: 'Subscribe to LGBTQ+ Updates',
    mode: 'light',
    socialProof: 'Join fellow queer Londoners in the know.',
    images: { left: '/london-pride-1.png', right: '/london-pride-2.png' },
    useCustomComponent: true,
    accentBgClass: 'bg-purple-500',
    accentTextClass: 'text-purple-600',
    showFogOverlay: false,
  },
  {
    slug: 'markets',
    type: 'tag',
    title: 'Markets',
    headline: "London's Best Markets, Curated for You.",
    subheadline:
      'Find the best pop-ups, street food, vintage stalls, and more — weekly and free.',
    events: ['markets_and_shopping', 'shopping'],
    primaryColor: 'green',
    ctaText: 'Subscribe to Market Updates',
    mode: 'light',
    socialProof: 'Join fellow market-lovers who never miss a hidden gem.',
    images: { left: '/london-markets-1.png', right: '/bethnal-green-2.png' },
    accentBgClass: 'bg-green-500',
    accentTextClass: 'text-green-600',
    showFogOverlay: false,
  }
] satisfies Omit<NewsletterConfig, 'theme'>[]).map((config: Omit<NewsletterConfig, 'theme'>) => ({
  ...config,
  theme: generateThemeFromConfig(config),
}));
