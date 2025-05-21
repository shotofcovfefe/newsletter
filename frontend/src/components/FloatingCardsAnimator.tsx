// src/components/FloatingCardsAnimator.tsx
'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import Image from 'next/image'; // Import if your FloatingEventBackgroundCard might use it
import clsx from 'clsx';

// --- Type Definitions ---
export interface PageEventData {
  id: number | string;
  card_title: string | null;
  card_vibes?: string | null;
  preview_image_url?: string | null;
  venue_name: string | null;
  card_blurb: string | null;
  type_badge: string | null;
  card_date_line?: string | null;
}

export interface NewsletterConfig {
  slug: string;
  theme?: {
    mode: 'light' | 'dark';
  };
}
// --- End Type Definitions ---

// --- FloatingEventBackgroundCard_Renderer ---
// Internal padding reverted to px-4 to match your original component
function FloatingEventBackgroundCard_Renderer({
  event,
  cfg,
}: {
  event: PageEventData;
  cfg: NewsletterConfig;
}) {
  const t = cfg.theme ?? { mode: 'light' };
  const dark = t.mode === 'dark';

  const badgeColour = dark
    ? 'bg-indigo-400/15 text-indigo-300'
    : 'bg-indigo-600/10 text-indigo-600';

  return (
    <article
      className={clsx(
        'flex flex-col h-full w-full rounded-lg border shadow-xl backdrop-blur-md',
        dark ? 'bg-neutral-800/80 border-neutral-700' : 'bg-white/85 border-neutral-300'
      )}
    >
      {event.type_badge && (
        <div className="flex justify-end px-3 pt-2">
          <span
            className={clsx(
              'inline-block text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full',
              badgeColour
            )}
          >
            {event.type_badge}
          </span>
        </div>
      )}
      {/* Main content div reverted to px-4 */}
      <div className="flex flex-col flex-grow px-4 pb-4 pt-1 text-center space-y-1 justify-center">
        {event.card_title && (
          <h3
            className={clsx(
              'text-sm font-semibold leading-snug',
              dark ? 'text-neutral-100' : 'text-neutral-900'
            )}
          >
            {event.card_title}
          </h3>
        )}
        {event.venue_name && (
          <p
            className={clsx(
              'text-xs italic',
              dark ? 'text-neutral-300' : 'text-neutral-600'
            )}
          >
            {event.venue_name}
          </p>
        )}
        {event.card_date_line && (
          <p
            className={clsx(
              'text-xs font-medium',
              dark ? 'text-emerald-400' : 'text-emerald-600'
            )}
          >
            {event.card_date_line}
          </p>
        )}
        {event.card_blurb && (
          <p
            className={clsx(
              'text-[11px] leading-tight line-clamp-3',
              dark ? 'text-neutral-300' : 'text-neutral-600'
            )}
          >
            {event.card_blurb}
          </p>
        )}
      </div>
    </article>
  );
}
// --- End FloatingEventBackgroundCard_Renderer ---

interface AnimatedCardState {
  id: number | string;
  x: number; y: number;
  vx: number; vy: number;
  scale: number; rotation: number;
  width: number; // Base width before this card's specific scale transform
  heightForPhysics: number; // Approx height for physics, based on original fixed ratio
  originalIndex: number;
}

interface FloatingCardsAnimatorProps {
  events: PageEventData[];
  cfg: NewsletterConfig;
  baseCardWidth: number;
  baseCardHeight: number; // This will now be used for physics approx. rather than direct styling
  isPageDark: boolean;
}

const getRandom = (min: number, max: number) => Math.random() * (max - min) + min;

export default function FloatingCardsAnimator({
  events,
  cfg,
  baseCardWidth,
  baseCardHeight, // Still used for physics height approximation
  isPageDark,
}: FloatingCardsAnimatorProps) {
  const [animatedCards, setAnimatedCards] = useState<AnimatedCardState[]>([]);
  const animationFrameId = useRef<number | null>(null);
  const viewportSize = useRef({ width: 0, height: 0 });

  useEffect(() => {
    const handleResize = () => {
      viewportSize.current = { width: window.innerWidth, height: window.innerHeight };
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    if (viewportSize.current.width === 0 || !events || events.length === 0) return;

    const initialStates: AnimatedCardState[] = events.map((event, index) => {
      const scale = getRandom(0.85, 1.1);
      const rotation = getRandom(-10, 10);

      // For physics, we'll use the scaled version of baseCardHeight.
      // The visual height will be auto.
      const physicsHeight = baseCardHeight * scale;
      const displayWidth = baseCardWidth * scale; // The effective width after this card's scale for collision

      return {
        id: event.id,
        x: getRandom(0, Math.max(0, viewportSize.current.width - displayWidth)),
        y: getRandom(0, Math.max(0, viewportSize.current.height - physicsHeight)),
        vx: getRandom(0.3, 0.8) * (Math.random() > 0.5 ? 1 : -1),
        vy: getRandom(0.3, 0.8) * (Math.random() > 0.5 ? 1 : -1),
        scale, rotation,
        width: displayWidth, // Use scaled width for collision
        heightForPhysics: physicsHeight, // Use scaled heightForPhysics for collision
        originalIndex: index,
      };
    });
    setAnimatedCards(initialStates);
  }, [events, baseCardWidth, baseCardHeight, viewportSize.current.width]);


  const animationLoop = useCallback(() => {
    if(viewportSize.current.width === 0) {
        animationFrameId.current = requestAnimationFrame(animationLoop);
        return;
    }
    setAnimatedCards(prevCards =>
      prevCards.map(card => {
        let newX = card.x + card.vx;
        let newY = card.y + card.vy;
        let newVx = card.vx;
        let newVy = card.vy;

        // Collision detection uses card.width (which is baseCardWidth * card.scale)
        // and card.heightForPhysics (which is baseCardHeight * card.scale)
        if (newX + card.width >= viewportSize.current.width) {
          newX = viewportSize.current.width - card.width;
          newVx = -Math.abs(card.vx);
        } else if (newX <= 0) {
          newX = 0;
          newVx = Math.abs(card.vx);
        }

        if (newY + card.heightForPhysics >= viewportSize.current.height) {
          newY = viewportSize.current.height - card.heightForPhysics;
          newVy = -Math.abs(card.vy);
        } else if (newY <= 0) {
          newY = 0;
          newVy = Math.abs(card.vy);
        }

        if (newVx === 0 && newVy === 0) {
            newVx = (Math.random() > 0.5 ? 1 : -1) * 0.5;
            newVy = (Math.random() > 0.5 ? 1 : -1) * 0.5;
        }

        return { ...card, x: newX, y: newY, vx: newVx, vy: newVy };
      })
    );
    animationFrameId.current = requestAnimationFrame(animationLoop);
  }, []);

  useEffect(() => {
    if (animatedCards.length > 0 && viewportSize.current.width > 0) {
      animationFrameId.current = requestAnimationFrame(animationLoop);
    }
    return () => {
      if (animationFrameId.current) {
        cancelAnimationFrame(animationFrameId.current);
      }
    };
  }, [animatedCards.length, animationLoop]);

  const [staticOpacities] = useState(() => {
    const opacities = isPageDark
      ? ['opacity-55', 'opacity-60', 'opacity-65']
      : ['opacity-65', 'opacity-70', 'opacity-75'];
    return events.map((_, index) => opacities[index % opacities.length]);
  });

  if (!animatedCards.length) return null;

  return (
    <>
      {animatedCards.map((cardState) => {
        const eventData = events.find(e => e.id === cardState.id);
        if (!eventData) return null;

        return (
          <div
            key={cardState.id}
            className={clsx(
              'fixed pointer-events-none',
              'hidden sm:block',
              staticOpacities[cardState.originalIndex],
              `z-[${5 + cardState.originalIndex}]`
            )}
            style={{
              width: `${baseCardWidth}px`, // Set base width before individual scale
              // REMOVED: height: `${baseCardHeight}px`,
              transform: `translateX(${cardState.x}px) translateY(${cardState.y}px) scale(${cardState.scale}) rotate(${cardState.rotation}deg)`,
              willChange: 'transform',
            }}
          >
            <FloatingEventBackgroundCard_Renderer event={eventData} cfg={cfg} />
          </div>
        );
      })}
    </>
  );
}