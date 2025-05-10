// src/app/newsletters/page.tsx
'use client'

import Link from 'next/link'
import { newsletterConfigs } from '@/config/newsletterConfigs'
import clsx from 'clsx'

type SectionKey = 'Neighbourhoods' | 'Tags & moods' | 'Other'

export default function NewslettersIndexPage() {
  // Group configs by type
  const sections: Record<SectionKey, typeof newsletterConfigs> = {
    Neighbourhoods: newsletterConfigs.filter(c => c.type === 'neighbourhood'),
    'Tags & moods': newsletterConfigs.filter(c => c.type === 'tag'),
    Other: newsletterConfigs.filter(c => !['neighbourhood', 'tag'].includes(c.type)),
  }

  return (
    <div className="min-h-screen bg-[#F5F2EE] dark:bg-neutral-950 text-neutral-900 dark:text-neutral-100 px-6 py-16">
      <h1 className="text-4xl sm:text-5xl font-serif font-semibold text-center mb-12">
        Our Curated Newsletters
      </h1>

      {Object.entries(sections).map(([title, list]) =>
        list.length ? (
          <section key={title} className="mb-16 max-w-6xl mx-auto">
            <h2 className="text-2xl font-serif font-medium mb-6">{title}</h2>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
              {list.map(cfg => (
                <div
                  key={cfg.slug}
                  className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-6 flex flex-col justify-between transition-shadow hover:shadow-md"
                >
                  <div>
                    <h3 className={clsx('text-lg font-semibold font-serif mb-2', cfg.accentTextClass)}>
                      {cfg.title}
                    </h3>

                    <p className="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed mb-6">
                      {cfg.subheadline}
                    </p>
                  </div>

                  <Link href={`/${cfg.slug}`} legacyBehavior>
                    <a
                      className={clsx(
                        'inline-flex items-center gap-1 text-sm font-medium underline underline-offset-2',
                        cfg.accentTextClass,
                        'hover:no-underline'
                      )}
                    >
                      Visit page →
                    </a>
                  </Link>
                </div>
              ))}
            </div>
          </section>
        ) : null
      )}
    </div>
  )
}
