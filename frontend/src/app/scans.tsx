import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { FlatList, Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { listScans, mediaUrl, type ScanSummary } from '@/api/client';
import { Button, EmptyState, ErrorState, Loading, Pill } from '@/components/ui-kit';
import { Accent, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

/**
 * Every scan ever taken, newest first, with how many books still need a
 * decision. Leaving the review queue no longer strands the scan — it is here
 * until it is finished.
 */
export default function ScansScreen() {
  const theme = useTheme();
  const [scans, setScans] = useState<ScanSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setScans(await listScans());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load your scans.');
    }
  }, []);

  // Refetch on focus so counts are right after coming back from a review.
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  if (error && !scans) return <ErrorState message={error} onRetry={load} />;
  if (!scans) return <Loading label="Loading your scans..." />;

  if (scans.length === 0) {
    return (
      <EmptyState
        title="No scans yet"
        body="Photograph a shelf and it will show up here, along with anything still waiting to be reviewed."
        action={<Button label="Scan a shelf" onPress={() => router.replace('/')} />}
      />
    );
  }

  return (
    <FlatList
      contentContainerStyle={styles.container}
      data={scans}
      keyExtractor={(scan) => String(scan.id)}
      renderItem={({ item }) => {
        const total = Object.values(item.counts).reduce((a, b) => a + b, 0);
        return (
          <Pressable
            onPress={() =>
              router.push({ pathname: '/scan/[id]', params: { id: String(item.id) } })
            }
            style={({ pressed }) => [
              styles.row,
              { backgroundColor: theme.backgroundElement, opacity: pressed ? 0.85 : 1 },
            ]}>
            {item.image_url ? (
              <Image
                source={{ uri: mediaUrl(item.image_url) }}
                style={styles.thumb}
                resizeMode="cover"
              />
            ) : (
              <View style={[styles.thumb, { backgroundColor: theme.backgroundSelected }]} />
            )}
            <View style={styles.body}>
              <Text style={[styles.title, { color: theme.text }]}>
                {new Date(item.created_at).toLocaleString()}
              </Text>
              <Text style={[styles.meta, { color: theme.textSecondary }]}>
                {total} {total === 1 ? 'spine' : 'spines'} · {item.counts.matched} matched
              </Text>
              {item.pending > 0 ? (
                <Pill label={`${item.pending} to review`} color={Accent.review} />
              ) : (
                <Text style={[styles.meta, { color: theme.textSecondary }]}>All reviewed</Text>
              )}
            </View>
          </Pressable>
        );
      }}
      ListFooterComponent={
        <View style={styles.footer}>
          <Button label="Scan a new shelf" variant="secondary" onPress={() => router.replace('/')} />
        </View>
      }
    />
  );
}

const styles = StyleSheet.create({
  container: { padding: Spacing.three, gap: Spacing.two, maxWidth: 640, width: '100%', alignSelf: 'center' },
  row: {
    flexDirection: 'row',
    gap: Spacing.three,
    padding: Spacing.two,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: Accent.border,
    alignItems: 'center',
  },
  thumb: { width: 64, height: 64, borderRadius: 6 },
  body: { flex: 1, gap: 4 },
  title: { fontSize: 15, fontWeight: '600' },
  meta: { fontSize: 13 },
  footer: { marginTop: Spacing.three },
});
