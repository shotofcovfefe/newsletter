import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  { auth: { persistSession: false } }
)


/**
 * Pull the 3 most relevant events for a newsletter slug.
 * You decide what “relevant” means – here we use a minimal filter.
 */
export async function getNewsletterEvents(slug: string) {
  const { data, error } = await supabase
    .from('events_enriched')
    .select(
      `
        id,
        card_title,
        venue_name,
        card_blurb,
        card_date_line,
        preview_image_url
      `
    )
    .limit(3)
    .order('start_date', { ascending: true })
    .ilike('card_vibes', `%${slug}%`)   // crude “tag” match
    .or(`audience_badges.ilike.%${slug}%`)
    .or(`event_types.ilike.%${slug}%`)

  if (error) {
    console.error('Supabase error', error)
    return []
  }
  return data
}