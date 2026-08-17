import type { ScanStatus } from '@/api/client';

/** One place to decide how a status looks and reads, so the results list and
 * the review queue never disagree about what "review" means. */
export const STATUS_META: Record<
  ScanStatus,
  { label: string; color: string; needsReview: boolean }
> = {
  matched: { label: 'Matched', color: '#1B873F', needsReview: false },
  review: { label: 'Needs review', color: '#B8860B', needsReview: true },
  unmatched: { label: 'Not in catalog', color: '#C2410C', needsReview: true },
  unreadable: { label: 'Unreadable', color: '#6B7280', needsReview: true },
  skipped: { label: 'Skipped', color: '#6B7280', needsReview: true },
};
