/**
 * poppy-1, from https://tweakcn.com/themes/cmlmbzwyz000004l72j9s6i76
 *
 * The source theme is authored in oklch, which React Native cannot parse, so
 * every colour here is the sRGB conversion of the published oklch value.
 * The theme's own radius (1rem) and Plus Jakarta Sans / Space Mono families
 * are carried over too.
 */
import { Platform } from 'react-native';

export const palette = {
  light: {
    background: '#F7F9F3',
    foreground: '#000000',
    card: '#FFFFFF',
    cardForeground: '#000000',
    popover: '#FFFFFF',
    primary: '#4F46E5',
    primaryForeground: '#FFFFFF',
    secondary: '#14B8A6',
    secondaryForeground: '#FFFFFF',
    muted: '#F0F0F0',
    mutedForeground: '#333333',
    accent: '#F59E0B',
    accentForeground: '#000000',
    destructive: '#EF4444',
    destructiveForeground: '#FFFFFF',
    // The theme's literal border is pure black, which is its signature look:
    // flat cards with a hard outline and almost no shadow.
    border: '#000000',
    input: '#737373',
    ring: '#A5B4FC',
    success: '#22C55E',
    chart: ['#4F46E5', '#14B8A6', '#F59E0B', '#EC4899', '#22C55E'],
    // A softer line for dividers inside a card, where a full black rule would
    // fight the card's own outline.
    hairline: '#E4E4E7',
    overlay: 'rgba(0,0,0,0.45)',
  },
  dark: {
    background: '#000000',
    foreground: '#FFFFFF',
    card: '#1A212B',
    cardForeground: '#FFFFFF',
    popover: '#1A212B',
    primary: '#818CF8',
    primaryForeground: '#000000',
    secondary: '#2DD4BF',
    secondaryForeground: '#000000',
    muted: '#333333',
    mutedForeground: '#CCCCCC',
    accent: '#FCD34D',
    accentForeground: '#000000',
    destructive: '#F87171',
    destructiveForeground: '#000000',
    border: '#545454',
    input: '#FFFFFF',
    ring: '#818CF8',
    success: '#4ADE80',
    chart: ['#818CF8', '#2DD4BF', '#FCD34D', '#F472B6', '#4ADE80'],
    hairline: '#2A3340',
    overlay: 'rgba(0,0,0,0.6)',
  },
};

export type Colors = typeof palette.light;

/** radius: 1rem in the source theme. */
export const radius = { sm: 8, md: 12, lg: 16, xl: 20, pill: 999 };

/** spacing: 0.25rem base, so these are the 4px steps the theme implies. */
export const spacing = {
  xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32,
};

/**
 * Plus Jakarta Sans and Space Mono are loaded at startup (see useAppFonts).
 * Until they report ready the app renders with the platform default, so these
 * names must only be used once `fontsLoaded` is true.
 */
export const fonts = {
  sans: 'PlusJakartaSans_400Regular',
  medium: 'PlusJakartaSans_500Medium',
  semibold: 'PlusJakartaSans_600SemiBold',
  bold: 'PlusJakartaSans_700Bold',
  mono: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' })!,
};

export const type = {
  display: { fontSize: 28, lineHeight: 34, letterSpacing: -0.6 },
  title: { fontSize: 21, lineHeight: 27, letterSpacing: -0.4 },
  heading: { fontSize: 17, lineHeight: 23, letterSpacing: -0.2 },
  body: { fontSize: 15, lineHeight: 21 },
  small: { fontSize: 13, lineHeight: 18 },
  caption: { fontSize: 11, lineHeight: 15, letterSpacing: 0.3 },
};

/**
 * poppy-1's shadows are nearly flat (0px blur, 0.05 alpha): the outline does
 * the work, not the shadow. Elevation is kept low so Android matches.
 */
export const shadow = {
  card: {
    shadowColor: '#1A1A1A',
    shadowOpacity: 0.05,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
    elevation: 1,
  },
  raised: {
    shadowColor: '#1A1A1A',
    shadowOpacity: 0.08,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 3 },
    elevation: 4,
  },
};
