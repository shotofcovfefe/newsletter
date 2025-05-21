// src/components/EventPreviewCard.tsx
'use client'
import Image from 'next/image'
import clsx from 'clsx'
import { NewsletterConfig } from '@/config/newsletterConfigs' // Import your main config type

export interface EventPreview {
  id: number
  card_title: string | null
  venue_name: string | null
  card_date_line: string | null
  card_vibes: string | null
  preview_image_url: string | null
  event_url: string | null
}

// Define a simplified theme type or use relevant parts from NewsletterConfig['theme']
interface CardThemeProps {
  mode: 'light' | 'dark';
  accentColor?: string; // e.g., text-emerald-600
  cardVibesColor?: string; // e.g., text-purple-600
  cardSubtitleColor?: string; // e.g., text-neutral-500
  cardTitleColor?: string; // e.g., text-neutral-900
  cardBorderColor?: string; // e.g., border-neutral-200
  cardBackgroundColor?: string; // e.g., bg-white
}

export default function EventPreviewCard({ 
  ev, 
  theme // Accept theme props
}: { 
  ev: EventPreview,
  theme: CardThemeProps
}) {
  const isDark = theme.mode === 'dark';

  return (
    <a
      href={ev.event_url ?? '#'}
      target="_blank"
      rel="noopener noreferrer"
      className={clsx(
        'group flex gap-3 rounded-lg border overflow-hidden',
        'hover:shadow-lg transition-shadow duration-200', // Slightly larger shadow on hover
        theme.cardBorderColor ? theme.cardBorderColor : (isDark ? 'border-neutral-700' : 'border-neutral-200'),
        theme.cardBackgroundColor ? theme.cardBackgroundColor : (isDark ? 'bg-neutral-800' : 'bg-white')
      )}
    >
      {/* thumbnail */}
      {ev.preview_image_url && (
        <div className="relative w-24 shrink-0"> {/* Consider increasing width: w-28 or w-32 */}
          <Image
            src={ev.preview_image_url}
            alt={ev.card_title ?? ''}
            fill
            sizes="(max-width: 768px) 96px, 128px" // Adjusted sizes
            className="object-cover group-hover:scale-105 transition-transform duration-300"
          />
        </div>
      )}

      {/* text */}
      <div className="py-3 pr-3 flex flex-col flex-grow min-w-0"> {/* Added flex-grow and min-w-0 for better text wrapping */}
        <h4 className={clsx(
            "text-sm font-semibold leading-snug line-clamp-2 mb-0.5",
            theme.cardTitleColor ? theme.cardTitleColor : (isDark ? 'text-neutral-100' : 'text-neutral-900')
          )}>
          {ev.card_title}
        </h4>
        {ev.venue_name && (
          <p className={clsx(
              "text-xs line-clamp-1 mb-0.5",
              theme.cardSubtitleColor ? theme.cardSubtitleColor : (isDark ? 'text-neutral-400' : 'text-neutral-500')
            )}>
            {ev.venue_name}
          </p>
        )}
        {ev.card_vibes && ( // Display card_vibes
          <p className={clsx(
            "text-xs font-medium line-clamp-1 mb-1", // Style for vibes
            theme.cardVibesColor ? theme.cardVibesColor : (isDark ? 'text-sky-400' : 'text-sky-600') // Example color
          )}>
            Vibes: {ev.card_vibes}
          </p>
        )}
        {/* Ensure date line is pushed to the bottom */}
        <div className="mt-auto"> 
          {ev.card_date_line && (
            <p className={clsx(
                "text-xs font-medium", 
                theme.accentColor ? theme.accentColor : (isDark ? 'text-emerald-400' : 'text-emerald-600')
              )}>
              {ev.card_date_line}
            </p>
          )}
        </div>
      </div>
    </a>
  )
}