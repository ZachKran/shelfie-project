import { Stack, ThemeProvider, type Theme } from 'expo-router';

import { Accent, Colors } from '@/constants/theme';

/** One theme regardless of system appearance — see constants/theme.ts. */
const paperTheme: Theme = {
  dark: false,
  colors: {
    primary: Accent.primary,
    background: Colors.light.background,
    card: Colors.light.background,
    text: Colors.light.text,
    border: Accent.border,
    notification: Accent.danger,
  },
  fonts: {
    regular: { fontFamily: 'System', fontWeight: '400' },
    medium: { fontFamily: 'System', fontWeight: '500' },
    bold: { fontFamily: 'System', fontWeight: '600' },
    heavy: { fontFamily: 'System', fontWeight: '700' },
  },
};

export default function RootLayout() {
  return (
    <ThemeProvider value={paperTheme}>
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: Colors.light.background },
          headerTintColor: Colors.light.text,
          contentStyle: { backgroundColor: Colors.light.background },
        }}>
        <Stack.Screen name="index" options={{ title: 'Shelfie' }} />
        <Stack.Screen name="scans" options={{ title: 'Your scans' }} />
        <Stack.Screen name="scan/[id]" options={{ title: 'Scan results' }} />
        <Stack.Screen name="review/[id]" options={{ title: 'Review' }} />
        <Stack.Screen name="library" options={{ title: 'My library' }} />
      </Stack>
    </ThemeProvider>
  );
}
