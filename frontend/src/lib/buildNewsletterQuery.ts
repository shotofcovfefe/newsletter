import { SupabaseClient } from '@supabase/supabase-js'
import { NewsletterConfig } from '@/config/newsletterConfigs'

/**
 * Builds a consistent query for newsletter events based on config type
 * @param supabase - Supabase client instance
 * @param config - Newsletter configuration
 * @param selectFields - Fields to select in the query
 * @param options - Additional query options (order, limit)
 * @returns A promise that resolves to deduplicated event results
 */
export async function buildNewsletterQuery(
  supabase: SupabaseClient,
  config: NewsletterConfig,
  selectFields: string,
  options: {
    limit?: number;
    orderBy?: { 
      column: string; 
      ascending: boolean; 
      nullsFirst?: boolean;
    }[];
    deduplicate?: boolean; // Whether to deduplicate results
    futureDatesOnly?: boolean; // Only include events from today onwards
  } = {}
) {
  // Generate today's date in ISO format for filtering (YYYY-MM-DD)
  const today = new Date().toISOString().split('T')[0];

  // Base query with select fields
  let query = supabase
    .from('events_enriched')
    .select(selectFields)
  
  // Filter for future events if requested
  if (options.futureDatesOnly) {
    query = query.gte('start_date', today);
  }

  // Add ordering if provided
  if (options.orderBy && options.orderBy.length > 0) {
    options.orderBy.forEach(orderOption => {
      query = query.order(orderOption.column, { 
        ascending: orderOption.ascending,
        nullsFirst: orderOption.nullsFirst
      })
    })
  }

  // Build filters based on newsletter type
  if (config.type === 'tag' && Array.isArray(config.events)) {
    // Create conditions for each event tag
    const conditions = config.events.flatMap(tag => [
      `card_vibes_arr.cs.{"${tag}"}`,
      `event_types.cs.{"${tag}"}`,
      `audience_badges.cs.{"${tag}"}`
    ]);
    
    query = query.or(conditions.join(','))
  } else if (config.type === 'neighbourhood' && Array.isArray(config.events)) {
    // Create conditions for both neighbourhood and borough checks
    const conditions = config.events.flatMap(area => [
      `location_neighbourhood.eq.${area}`,
      `location_borough.eq.${area}`
    ]);
    
    query = query.or(conditions.join(','))
  }

  // We need to fetch more than requested limit for deduplication
  const fetchLimit = options.deduplicate ? 
    (options.limit ? options.limit * 3 : 20) : // Fetch 3x limit if deduplicating
    options.limit; 

  if (fetchLimit) {
    query = query.limit(fetchLimit)
  }

  // Execute query
  const { data, error } = await query

  // Handle error case
  if (error) {
    console.error('Newsletter query error:', error)
    return { data: [], error }
  }

  // Deduplicate results if requested
  if (options.deduplicate && data) {
    const deduplicatedData = deduplicateEvents(data)
    
    // Apply the original limit after deduplication
    const finalData = options.limit ? deduplicatedData.slice(0, options.limit) : deduplicatedData
    
    return { data: finalData, error: null }
  }

  return { data, error }
}

/**
 * Deduplicates events based on venue and title
 * @param events - Array of events to deduplicate
 * @returns Array of deduplicated events
 */
function deduplicateEvents(events: any[]) {
  const seenVenueTitlePairs = new Map();
  const seenTitles = new Map();
  
  return events.filter(event => {
    // Extract title and venue
    const venueKey = event.venue_name || '';
    const titleKey = event.card_title || '';
    
    // Skip events with the same title (regardless of venue)
    if (titleKey && seenTitles.has(titleKey.toLowerCase())) {
      return false;
    }
    
    // Skip events with the same venue+title combination
    const compositeKey = `${venueKey.toLowerCase()}:${titleKey.toLowerCase()}`;
    if (compositeKey !== ':' && seenVenueTitlePairs.has(compositeKey)) {
      return false;
    }
    
    // Remember this event's title and venue+title combination
    if (titleKey) {
      seenTitles.set(titleKey.toLowerCase(), true);
    }
    if (compositeKey !== ':') {
      seenVenueTitlePairs.set(compositeKey, true);
    }
    
    return true;
  });
} 