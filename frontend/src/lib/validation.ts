// src/lib/validation.ts
import * as z from 'zod';

// --- Shared Constants ---
export const interestTags = [
  'Art', 'Food & Drink', 'Live Music', 'Workshops',
  'Comedy', 'Markets', 'Families', 'Date Night', 'Solo Friendly'
] as const;

export const ukPostcodeRegex = /^([A-Z]{1,2}\d[A-Z\d]? ?\d[ABD-HJLNP-UW-Z]{2})$/i;

// --- Helper Function for London Postcode Validation ---
export function isLondonPostcode(postcode: string): boolean {
  if (!postcode) return false;
  // Normalize: remove all spaces, convert to uppercase.
  // Example: "sw1a 1aa" -> "SW1A1AA"; "E1  7AX" -> "E17AX"
  const normalizedPostcode = postcode.toUpperCase().replace(/\s+/g, "");

  // Define core London postcode area prefixes
  // To include Outer London, you would expand this list (e.g., add 'IG', 'RM', 'EN', 'HA', etc.)
  const coreLondonAreas = ['E', 'EC', 'N', 'NW', 'SE', 'SW', 'W', 'WC'];

  for (const area of coreLondonAreas) {
    if (normalizedPostcode.startsWith(area)) {
      // For 1-letter area codes (E, N, W), ensure the character immediately following
      // the area code is a digit. This distinguishes E# (East London) from EN# (Enfield),
      // N# (North London) from NW# (North West London - already handled as 'NW'), etc.
      if (area.length === 1) {
        const charAfterArea = normalizedPostcode.charAt(area.length);
        if (charAfterArea >= '0' && charAfterArea <= '9') {
          return true; // e.g., E1, N1, W1
        }
        // If not a digit (e.g., 'N' in 'EN1'), continue loop for other coreLondonAreas
        // as it might be a 2-letter area like 'NW' that we haven't checked yet.
      } else {
        // For 2-letter area codes (EC, NW, SE, SW, WC), a simple startsWith is sufficient
        // as these are distinct enough for our core list.
        return true; // e.g., EC1, NW3, SW1A
      }
    }
  }
  // If no core London area prefix matches according to the rules
  return false;
}

// --- Zod Schema for Subscription Form ---
export const subscriptionSchema = z.object({
  email:     z.string().email("Invalid email address"),
  postcode:  z.string().trim()
             .regex(ukPostcodeRegex, 'Please enter a valid London postcode')
             .refine(isLondonPostcode, {
               message: "Please enter a valid London postcode",
             }),
  interests: z.array(z.enum(interestTags)).min(1, 'Pick at least one interest'),
  website:   z.string().max(0, { message: "Bots only" }).optional(), // Honeypot field
  cfToken:   z.string().min(1, { message: "Captcha completion required" }), // Cloudflare Turnstile token
});

// --- Exported Type for Form Data ---
export type SubscriptionFormData = z.infer<typeof subscriptionSchema>;