// src/app/[slug]/page.tsx
import Image from 'next/image';
import { notFound } from 'next/navigation';
import clsx from 'clsx';
import { newsletterConfigs, NewsletterConfig } from '@/config/newsletterConfigs';
import SignupForm from '@/components/SignupForm';
import { getNewsletterEvents } from '@/lib/getNewsletterEvents';
import EventPreviewCard, { EventPreview } from '@/components/EventPreviewCard';
import FloatingCardsAnimator from '@/components/FloatingCardsAnimator';
import ThemeController from '@/components/ThemeController';
import FogOverlay from '@/components/FogOverlay';

export interface PageEventData extends EventPreview {
  id: number | string;
  venue_name: string | null;
  card_blurb: string | null;
  type_badge: string | null;
  card_date_line?: string | null;
}

export default async function NewsletterPage({
  params,
}: {
  params: { slug: string };
}) {
  const slug = params.slug.toLowerCase();
  const cfg = newsletterConfigs.find(c => c.slug === slug);

  if (!cfg) {
    notFound();
  }

  const pageTheme = cfg.theme ?? { mode: 'light' };
  const pageDisplayMode = cfg.mode || pageTheme.mode || 'light';
  const isPageDark = pageDisplayMode === 'dark';

  const mainTextColor = isPageDark ? (pageTheme.mainTextColor || 'text-neutral-200') : (pageTheme.mainTextColor || 'text-neutral-800');
  const heroHeadlineColor = isPageDark ? (pageTheme.heroHeadlineColor || 'text-neutral-100') : (pageTheme.heroHeadlineColor || 'text-neutral-900');
  const heroSubheadlineColor = isPageDark ? (pageTheme.heroSubheadlineColor || 'text-neutral-300') : (pageTheme.heroSubheadlineColor || 'text-neutral-600');
  const signupContainerBg = isPageDark ? (pageTheme.signupContainerBg || 'bg-neutral-800/70') : (pageTheme.signupContainerBg || 'bg-white/70');
  const socialProofColor = isPageDark ? (pageTheme.socialProofColor || 'text-neutral-400') : (pageTheme.socialProofColor || 'text-neutral-500');
  const cornerImageOpacity = isPageDark ? (pageTheme.cornerImageOpacity || 'opacity-40') : (pageTheme.cornerImageOpacity || 'opacity-60');

  const rawEvents = await getNewsletterEvents(slug);
  const allEvents: PageEventData[] = rawEvents.map((event, index) => ({
    ...event,
    id: event.id || `event-${slug}-${Date.now()}-${index}`,
  }));

  const MAX_FLOATING_CARDS = 3;
  const eventsForFloatingEffect = allEvents.slice(0, Math.min(allEvents.length, MAX_FLOATING_CARDS));
  const eventsForMainGrid = allEvents.slice(eventsForFloatingEffect.length);

  const BASE_CARD_WIDTH = 200;
  const BASE_CARD_HEIGHT = Math.round(BASE_CARD_WIDTH * (3 / 2));

  return (
    <>
      <ThemeController mode={pageDisplayMode} />
      <main className={clsx("flex flex-col min-h-screen overflow-x-hidden", mainTextColor)}>

        {cfg.showFogOverlay && <FogOverlay />}

        {eventsForFloatingEffect.length > 0 && (
          <FloatingCardsAnimator
            events={eventsForFloatingEffect}
            cfg={cfg}
            baseCardWidth={BASE_CARD_WIDTH}
            baseCardHeight={BASE_CARD_HEIGHT}
            isPageDark={isPageDark}
          />
        )}

        <section className={clsx(
          "relative flex flex-col items-center justify-center text-center space-y-8 md:space-y-10 flex-grow",
          "px-4 py-12 sm:px-6 sm:py-16",
          "z-[20]"
        )}>
          <h1 className={clsx("mx-auto max-w-4xl md:max-w-5xl text-4xl sm:text-5xl lg:text-6xl font-serif font-semibold leading-tight tracking-tight", heroHeadlineColor)}>
            {cfg.headline}
          </h1>
          <p className={clsx("mx-auto max-w-lg md:max-w-xl text-lg sm:text-xl", heroSubheadlineColor)}>
            {cfg.subheadline}
          </p>
          {/* MODIFIED: Changed md:max-w-2xl to md:max-w-lg for the wrapper div */}
          {/* This will make the backdrop-blurred box narrower on md screens and up. */}
          {/* You can also use max-w-xl if max-w-lg is too narrow. */}
          <div className={clsx(
            "w-full max-w-md sm:max-w-lg rounded-xl backdrop-blur-lg shadow-2xl",
            // Using max-w-md for smallest, sm:max-w-lg for small and up.
            // This ensures the SignupForm (which is max-w-xl internally) gets constrained.
            signupContainerBg
          )}>
            <SignupForm
              events={cfg.events}
              mode={pageDisplayMode}
              primaryColor={cfg.primaryColor || pageTheme.accentColor}
              ctaText={cfg.ctaText}
              newsletterSlug={cfg.slug}
            />
          </div>
          {cfg.socialProof && (
            <p className={clsx("text-sm", socialProofColor)}>{cfg.socialProof}</p>
          )}
        </section>

        {eventsForMainGrid.length > 0 && (
          <section className={clsx(
            "relative mx-auto mt-12 mb-20 md:mb-24 w-full max-w-xl md:max-w-2xl lg:max-w-3xl px-4",
            "z-[20]"
          )}>
            <div className="grid grid-cols-1 gap-4 md:gap-5">
              {eventsForMainGrid.map(event => {
                const cardThemeForGrid = {
                  mode: pageDisplayMode,
                  accentColor: pageTheme.accentColor || (isPageDark ? 'text-emerald-400' : 'text-emerald-600'),
                  cardVibesColor: pageTheme.cardVibesColor || (isPageDark ? 'text-sky-400' : 'text-sky-600'),
                  cardSubtitleColor: pageTheme.cardSubtitleColor || (isPageDark ? 'text-neutral-400' : 'text-neutral-500'),
                  cardTitleColor: pageTheme.cardTitleColor || (isPageDark ? 'text-neutral-100' : 'text-neutral-900'),
                  cardBorderColor: pageTheme.cardBorderColor || (isPageDark ? 'border-neutral-700' : 'border-neutral-200'),
                  cardBackgroundColor: pageTheme.cardBackgroundColor || (isPageDark ? 'bg-neutral-800' : 'bg-white'),
                };
                return (
                  <EventPreviewCard
                    key={`interactive-card-${event.id}`}
                    ev={event}
                    theme={cardThemeForGrid}
                  />
                );
              })}
            </div>
          </section>
        )}

        {cfg.images && (
          <>
            <div className={clsx("hidden md:block fixed bottom-0 left-0 m-4 lg:m-8 pointer-events-none", "z-[15]")}>
              <Image src={cfg.images.left} alt="" width={180} height={120} className={clsx("w-40 h-auto lg:w-44", cornerImageOpacity)} priority={false}/>
            </div>
            <div className={clsx("hidden md:block fixed bottom-0 right-0 m-4 lg:m-8 pointer-events-none", "z-[15]")}>
              <Image src={cfg.images.right} alt="" width={180} height={120} className={clsx("w-40 h-auto lg:w-44", cornerImageOpacity)} priority={false}/>
            </div>
          </>
        )}
      </main>
    </>
  );
}
