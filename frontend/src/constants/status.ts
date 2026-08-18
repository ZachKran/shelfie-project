import type { ScanStatus } from '@/api/client';

import { Accent } from './theme';

/** One place to decide how a status looks and reads, so the results list and
 * the review queue never disagree about what "review" means. */
export const STATUS_META: Record<
  ScanStatus,
  { label: string; color: string; needsReview: boolean }
> = {
  matched: { label: 'Matched', color: Accent.matched, needsReview: false },
  review: { label: 'Needs review', color: Accent.review, needsReview: true },
  unmatched: { label: 'Not in catalog', color: Accent.unmatched, needsReview: true },
  unreadable: { label: 'Unreadable', color: Accent.neutral, needsReview: true },
  skipped: { label: 'Skipped', color: Accent.neutral, needsReview: true },
};
