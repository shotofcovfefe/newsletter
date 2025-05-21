import { supabase } from '@/lib/supabase-browser'
import { newsletterConfigs } from '@/config/newsletterConfigs'
import { buildNewsletterQuery } from '@/lib/buildNewsletterQuery'

export async function getNewsletterEvents(slug: string) {
  const config = newsletterConfigs.find(c => c.slug.toLowerCase() === slug.toLowerCase())
  if (!config) return []

  const selectFields = 'id, card_title, venue_name, card_blurb, card_vibes, card_vibes_arr, card_date_line, event_types, audience_badges, preview_image_url, location_neighbourhood, location_borough'
  
  // Use the shared query building function with appropriate options
  const { data, error } = await buildNewsletterQuery(
    supabase,
    config,
    selectFields,
    {
      limit: 3,
      orderBy: [{ column: 'start_date', ascending: true }],
      futureDatesOnly: true, // Only show future events
      deduplicate: true      // Prevent duplicate venues/titles
    }
  )

  if (error) {
    console.error('getNewsletterEvents:', error)
    return []
  }

  return data || []
}
