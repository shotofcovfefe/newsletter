// src/app/newsletters/page.tsx
'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import Image from 'next/image'
import clsx from 'clsx'

import { newsletterConfigs, type NewsletterConfig } from '@/config/newsletterConfigs'

// 🔑 same client everywhere
import { supabase } from '@/lib/supabase-browser'
import { buildNewsletterQuery } from '@/lib/buildNewsletterQuery'

type SectionKey = 'Neighbourhoods' | 'Tags & moods' | 'Other'

interface PreviewEvent {
  id: number
  card_title: string | null
  card_date_line: string | null
  preview_image_url: string | null
  slug: string                       // ↞ added by the SQL so we can group
}

export default function NewslettersIndexPage() {
  const [previews, setPreviews] = useState<Record<string, PreviewEvent[]>>({})

  /* ───────── fetch previews once ───────── */
  useEffect(() => {
    let cancelled = false

    ;(async () => {
      // one round-trip per slug; keeps code simple & avoids a SQL function
      const rows: PreviewEvent[] = []

      await Promise.all(
        newsletterConfigs.map(async cfg => {
          // Define fields to select
          const selectFields = 'id, card_title, card_date_line, preview_image_url'
          
          // Build the query using the shared utility
          const query = buildNewsletterQuery(
            supabase,
            cfg,
            selectFields,
            {
              limit: 3,
              orderBy: [
                { column: 'start_date', ascending: true, nullsFirst: false },
                { column: 'created_at', ascending: false }
              ],
              futureDatesOnly: true,
              deduplicate: true
            }
          )

          // Execute the query
          const { data, error } = await query
          
          // Handle errors
          if (error) {
            console.error('preview fetch error', cfg.slug, error)
            return
          }
          
          // Process results
          if (data) {
            for (const item of data as any[]) {
              rows.push({
                id: item.id,
                card_title: item.card_title,
                card_date_line: item.card_date_line,
                preview_image_url: item.preview_image_url,
                slug: cfg.slug
              })
            }
          }
        })
      )

      if (!cancelled) {
        const grouped: Record<string, PreviewEvent[]> = {}
        rows.forEach(ev => {
          grouped[ev.slug] = [...(grouped[ev.slug] ?? []), ev]
        })
        setPreviews(grouped)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  /* ───────── group configs for UI ───────── */
  const sections: Record<SectionKey, NewsletterConfig[]> = {
    Neighbourhoods: newsletterConfigs.filter(c => c.type === 'neighbourhood'),
    'Tags & moods': newsletterConfigs.filter(c => c.type === 'tag'),
    Other: newsletterConfigs.filter(c => !['neighbourhood', 'tag'].includes(c.type)),
  }

  /* ───────── render ───────── */
  return (
    <div className="min-h-screen bg-[#F5F2EE] dark:bg-neutral-950 text-neutral-900 dark:text-neutral-100 px-4 sm:px-6 py-12 sm:py-16">
      <header className="text-center mb-12 sm:mb-16">
        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-serif font-semibold">
          Our Curated Newsletters
        </h1>
        <p className="mt-3 text-lg text-neutral-600 dark:text-neutral-400 max-w-2xl mx-auto">
          Choose your focus. Get London events, unfogged.
        </p>
      </header>

      {Object.entries(sections).map(([title, list]) =>
        list.length ? (
          <section key={title} className="mb-20 max-w-7xl mx-auto">
            <h2 className="text-2xl sm:text-3xl font-serif font-medium mb-8 px-1 text-neutral-700 dark:text-neutral-300">
              {title}
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 sm:gap-8">
              {list.map(cfg => {
                const evs = previews[cfg.slug] ?? []

                return (
                  <div
                    key={cfg.slug}
                    className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 flex flex-col overflow-hidden transition hover:shadow-xl"
                  >
                    {/* hero image */}
                    {cfg.images?.left && (
                      <div className="relative h-48 sm:h-56">
                        <Image
                          src={cfg.images.left}
                          alt=""
                          fill
                          className="object-cover"
                        />
                      </div>
                    )}

                    <div className="p-5 flex flex-col flex-grow">
                      <h3
                        className={clsx(
                          'text-xl font-serif font-semibold mb-1',
                          cfg.accentTextClass || 'text-neutral-800 dark:text-neutral-100'
                        )}
                      >
                        {cfg.title}
                      </h3>

                      <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-4 line-clamp-3">
                        {cfg.subheadline}
                      </p>

                      {/* small previews */}
                      {evs.length > 0 && (
                        <ul className="space-y-2 mb-6">
                          {evs.map(ev => (
                            <li key={ev.id} className="flex items-start gap-2 text-sm">
                              {ev.preview_image_url && (
                                <Image
                                  src={ev.preview_image_url}
                                  alt=""
                                  width={36}
                                  height={36}
                                  className="rounded object-cover flex-none"
                                />
                              )}
                              <div className="leading-tight">
                                <p className="font-medium">{ev.card_title ?? 'Untitled event'}</p>
                                {ev.card_date_line && (
                                  <p className="text-xs text-neutral-500 dark:text-neutral-400">
                                    {ev.card_date_line}
                                  </p>
                                )}
                              </div>
                            </li>
                          ))}
                        </ul>
                      )}

                      <Link
                        href={`/${cfg.slug}`}
                        className={clsx(
                          'mt-auto inline-flex items-center justify-center gap-2 text-sm font-semibold py-2.5 px-4 rounded-lg transition',
                          cfg.accentBgClass
                            ? `${cfg.accentBgClass} text-white hover:opacity-90`
                            : `${cfg.accentTextClass} underline hover:no-underline`
                        )}
                      >
                        Visit page
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          viewBox="0 0 20 20"
                          fill="currentColor"
                          className="w-4 h-4"
                        >
                          <path
                            fillRule="evenodd"
                            d="M3 10a.75.75 0 01.75-.75h10.5a.75.75 0 010 1.5H3.75A.75.75 0 013 10z"
                            clipRule="evenodd"
                          />
                          <path
                            fillRule="evenodd"
                            d="M10.28 15.78a.75.75 0 010-1.06l2.47-2.47H3.75a.75.75 0 010-1.5h9l-2.47-2.47a.75.75 0 111.06-1.06l4 4a.75.75 0 010 1.06l-4 4a.75.75 0 01-1.06 0z"
                            clipRule="evenodd"
                          />
                        </svg>
                      </Link>
                    </div>
                  </div>
                )
              })}
            </div>
          </section>
        ) : null
      )}
    </div>
  )
}
