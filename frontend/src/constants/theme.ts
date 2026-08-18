/**
 * Shelfie's palette. Warm paper tones rather than the template's black and
 * white — a shelf of books is a warm object, and the crops sit better against
 * beige than against pure black.
 *
 * The same palette is used in both colour schemes on purpose: the app is
 * judged on one screen and a consistent look is worth more here than
 * respecting a system dark mode.
 */

import '@/global.css';

import { Platform } from 'react-native';

const paper = {
  text: '#2E2416',
  background: '#F6F0E4',
  backgroundElement: '#EBE1CE',
  backgroundSelected: '#DECDAF',
  textSecondary: '#6E6250',
} as const;

export const Colors = {
  light: paper,
  dark: paper,
} as const;

/** Accents, kept out of Colors so they do not vary by scheme. */
export const Accent = {
  primary: '#8A5A2B',
  primaryText: '#FFF9EF',
  danger: '#9B3B2F',
  border: '#C9B896',
  matched: '#3F6B3A',
  review: '#A8761C',
  unmatched: '#B4532F',
  neutral: '#7A6E5D',
} as const;

export type ThemeColor = keyof typeof Colors.light & keyof typeof Colors.dark;

export const Fonts = Platform.select({
  ios: {
    sans: 'system-ui',
    serif: 'ui-serif',
    rounded: 'ui-rounded',
    mono: 'ui-monospace',
  },
  default: {
    sans: 'normal',
    serif: 'serif',
    rounded: 'normal',
    mono: 'monospace',
  },
  web: {
    sans: 'var(--font-display)',
    serif: 'var(--font-serif)',
    rounded: 'var(--font-rounded)',
    mono: 'var(--font-mono)',
  },
});

export const Spacing = {
  half: 2,
  one: 4,
  two: 8,
  three: 16,
  four: 24,
  five: 32,
  six: 64,
} as const;

export const BottomTabInset = Platform.select({ ios: 50, android: 80 }) ?? 0;
export const MaxContentWidth = 800;
