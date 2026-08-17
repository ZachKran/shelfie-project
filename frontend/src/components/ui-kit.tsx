/** Small shared pieces so the four screens look like one app. */
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled,
  busy,
}: {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
  busy?: boolean;
}) {
  const theme = useTheme();
  const background =
    variant === 'primary' ? '#2563EB' : variant === 'danger' ? '#B91C1C' : theme.backgroundElement;
  const color = variant === 'secondary' ? theme.text : '#FFFFFF';
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={disabled || busy}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: background, opacity: disabled || busy ? 0.5 : pressed ? 0.85 : 1 },
      ]}>
      {busy ? <ActivityIndicator color={color} /> : <Text style={[styles.buttonText, { color }]}>{label}</Text>}
    </Pressable>
  );
}

export function Card({ children }: { children: React.ReactNode }) {
  const theme = useTheme();
  return <View style={[styles.card, { backgroundColor: theme.backgroundElement }]}>{children}</View>;
}

export function Pill({ label, color }: { label: string; color: string }) {
  return (
    <View style={[styles.pill, { backgroundColor: color }]}>
      <Text style={styles.pillText}>{label}</Text>
    </View>
  );
}

/** One consistent way to fail. Never a blank screen. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const theme = useTheme();
  return (
    <View style={styles.state}>
      <Text style={[styles.stateTitle, { color: theme.text }]}>Something went wrong</Text>
      <Text style={[styles.stateBody, { color: theme.textSecondary }]}>{message}</Text>
      {onRetry ? <Button label="Try again" onPress={onRetry} variant="secondary" /> : null}
    </View>
  );
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  const theme = useTheme();
  return (
    <View style={styles.state}>
      <Text style={[styles.stateTitle, { color: theme.text }]}>{title}</Text>
      <Text style={[styles.stateBody, { color: theme.textSecondary }]}>{body}</Text>
      {action}
    </View>
  );
}

export function Loading({ label }: { label: string }) {
  const theme = useTheme();
  return (
    <View style={styles.state}>
      <ActivityIndicator size="large" />
      <Text style={[styles.stateBody, { color: theme.textSecondary }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  button: {
    paddingVertical: 14,
    paddingHorizontal: Spacing.four,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 48,
  },
  buttonText: { fontSize: 16, fontWeight: '600' },
  card: { borderRadius: 12, padding: Spacing.three, gap: Spacing.two },
  pill: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999, alignSelf: 'flex-start' },
  pillText: { color: '#FFFFFF', fontSize: 12, fontWeight: '700' },
  state: { padding: Spacing.four, gap: Spacing.three, alignItems: 'center', justifyContent: 'center', flex: 1 },
  stateTitle: { fontSize: 18, fontWeight: '700', textAlign: 'center' },
  stateBody: { fontSize: 15, textAlign: 'center', lineHeight: 21 },
});
