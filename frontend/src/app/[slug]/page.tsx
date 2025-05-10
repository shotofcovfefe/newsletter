// src/app/[slug]/page.tsx
'use client'

import { notFound } from 'next/navigation'
import { newsletterConfigs } from '@/config/newsletterConfigs'
import SignupForm from '@/components/SignupForm'
import Image from 'next/image'

interface Props {
  params: { slug: string }
}

export default function NewsletterPage({ params }: Props) {
  const config = newsletterConfigs.find((cfg) => cfg.slug === params.slug)
  if (!config || config.useCustomComponent) return notFound()

  return (
    <main className="bg-white text-neutral-800 w-full min-h-screen flex flex-col">
      <section className="flex flex-col items-center justify-center px-6 py-16 sm:py-24 text-center space-y-12 flex-grow">
        <h1 className="text-5xl sm:text-6xl font-serif font-semibold leading-tight tracking-tight max-w-5xl mx-auto">
          {config.headline}
        </h1>

        <p className="text-lg sm:text-xl text-neutral-500 leading-relaxed max-w-xl mx-auto">
          {config.subheadline}
        </p>

        <div className="w-full max-w-xl bg-white/80 backdrop-blur-sm p-6 sm:p-8 rounded-xl shadow-xl mt-8">
          <SignupForm
            events={config.events}
            mode={config.mode}
            primaryColor={config.primaryColor}
            ctaText={config.ctaText}
            newsletterSlug={config.slug}
          />
        </div>

        <p className="text-sm text-neutral-500">{config.socialProof}</p>
      </section>

      {config.images && (
        <>
          <div className="hidden md:block fixed bottom-0 left-0 m-4 lg:m-8 z-0 pointer-events-none">
            <Image src={config.images.left} alt="" width={180} height={120} className="w-48 h-auto lg:w-44" />
          </div>
          <div className="hidden md:block fixed bottom-0 right-0 m-4 lg:m-8 z-0 pointer-events-none">
            <Image src={config.images.right} alt="" width={180} height={120} className="w-48 h-auto lg:w-44" />
          </div>
        </>
      )}
    </main>
  )
}
