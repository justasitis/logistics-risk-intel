import type { ReviewResponse } from '../types/mi'

/**
 * Existing Step 6 code that accepts the old canonical MI JSON can receive this
 * object without calling the external Gemini output directly.
 */
export function toLegacyMiPayload(review: ReviewResponse) {
  return review.canonical_payload
}
