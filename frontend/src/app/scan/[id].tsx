import { router, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { FlatList, Image, StyleSheet, Text, View } from 'react-native';

import { getScan, mediaUrl, resolveItem, type Scan, type ScanItem } from '@/api/client';
import { Button, Card, EmptyState, ErrorState, Loading, Pill } from '@/components/ui-kit';
import { STATUS_META } from '@/constants/status';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export default function ScanResultsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const theme = useTheme();
  const [scan, setScan] = useState<Scan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setScan(await getScan(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load this scan.');
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const pending = useMemo(
    () => (scan?.items ?? []).filter((i) => STATUS_META[i.status].needsReview && !i.resolved),
    [scan]
  );
  const matched = useMemo(
    () => (scan?.items ?? []).filter((i) => i.status === 'matched' && !i.resolved),
    [scan]
  );

  async function addAllMatched() {
    if (!scan) return;
    setAdding(true);
    try {
      // Sequential rather than parallel: the failure of one book should not
      // leave the others in an unknown state.
      for (const item of matched) {
        await resolveItem(item.id, 'confirm');
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add these books.');
    } finally {
      setAdding(false);
    }
  }

  if (error && !scan) return <ErrorState message={error} onRetry={load} />;
  if (!scan) return <Loading label="Loading scan..." />;

  if (scan.error) {
    return (
      <ErrorState
        message={`This scan did not finish: ${scan.error}`}
        onRetry={() => router.replace('/')}
      />
    );
  }

  if (scan.items.length === 0) {
    return (
      <EmptyState
        title="No books found"
        body="Nothing on this photo looked like a book spine. Try getting closer, filling the frame with one shelf, and keeping the camera square to the books."
        action={<Button label="Take another photo" onPress={() => router.replace('/')} />}
      />
    );
  }

  return (
    <FlatList
      contentContainerStyle={styles.container}
      data={scan.items}
      keyExtractor={(item) => String(item.id)}
      ListHeaderComponent={
        <View style={styles.header}>
          <Text style={[styles.title, { color: theme.text }]}>
            {scan.items.length} spines found
          </Text>
          <View style={styles.pills}>
            {(Object.keys(STATUS_META) as (keyof typeof STATUS_META)[])
              .filter((key) => (scan.counts[key] ?? 0) > 0)
              .map((key) => (
                <Pill
                  key={key}
                  label={`${scan.counts[key]} ${STATUS_META[key].label.toLowerCase()}`}
                  color={STATUS_META[key].color}
                />
              ))}
          </View>

          {matched.length > 0 ? (
            <Button
              label={`Add ${matched.length} confident ${matched.length === 1 ? 'match' : 'matches'}`}
              onPress={addAllMatched}
              busy={adding}
            />
          ) : null}

          {pending.length > 0 ? (
            <Button
              label={`Review ${pending.length} ${pending.length === 1 ? 'book' : 'books'}`}
              variant="secondary"
              onPress={() =>
                router.push({ pathname: '/review/[id]', params: { id: String(scan.id) } })
              }
            />
          ) : (
            <Text style={[styles.done, { color: theme.textSecondary }]}>
              Nothing left to review.
            </Text>
          )}

          {error ? <Text style={styles.inlineError}>{error}</Text> : null}
        </View>
      }
      renderItem={({ item }) => <ResultRow item={item} />}
      ListFooterComponent={<Timings scan={scan} />}
    />
  );
}

function ResultRow({ item }: { item: ScanItem }) {
  const theme = useTheme();
  const meta = STATUS_META[item.status];
  const top = item.candidates[0];
  return (
    <View style={[styles.row, { borderBottomColor: theme.backgroundElement }]}>
      {item.crop_url ? (
        <Image source={{ uri: mediaUrl(item.crop_url) }} style={styles.crop} resizeMode="cover" />
      ) : (
        <View style={[styles.crop, { backgroundColor: theme.backgroundElement }]} />
      )}
      <View style={styles.rowBody}>
        <Text style={[styles.rowTitle, { color: theme.text }]} numberOfLines={1}>
          {item.status === 'matched' && top ? top.title : item.read_title || 'Not readable'}
        </Text>
        <Text style={[styles.rowMeta, { color: theme.textSecondary }]} numberOfLines={1}>
          {item.status === 'matched' && top
            ? top.author
            : item.read_author || item.read_error || 'no author read'}
        </Text>
        <View style={styles.rowFooter}>
          <Pill label={meta.label} color={meta.color} />
          {item.confidence > 0 ? (
            <Text style={[styles.rowMeta, { color: theme.textSecondary }]}>
              {(item.confidence * 100).toFixed(0)}% confident
            </Text>
          ) : null}
          {item.resolved ? (
            <Text style={[styles.rowMeta, { color: theme.textSecondary }]}>done</Text>
          ) : null}
        </View>
      </View>
    </View>
  );
}

function Timings({ scan }: { scan: Scan }) {
  const theme = useTheme();
  const t = scan.timings;
  if (!t.total_ms) return null;
  return (
    <Card>
      <Text style={[styles.rowMeta, { color: theme.textSecondary }]}>
        detect {t.detect_ms ?? 0} ms · read {t.vlm_ms ?? 0} ms · match {t.match_ms ?? 0} ms ·
        total {t.total_ms} ms
      </Text>
      <Text style={[styles.rowMeta, { color: theme.textSecondary }]}>
        tokens in {t.vlm_input_tokens ?? 0} · out {t.vlm_output_tokens ?? 0}
      </Text>
    </Card>
  );
}

const styles = StyleSheet.create({
  container: { padding: Spacing.three, gap: Spacing.two, maxWidth: 640, width: '100%', alignSelf: 'center' },
  header: { gap: Spacing.two, marginBottom: Spacing.two },
  title: { fontSize: 22, fontWeight: '700' },
  pills: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.two },
  done: { fontSize: 14 },
  inlineError: { color: '#B91C1C', fontSize: 14 },
  row: { flexDirection: 'row', gap: Spacing.three, paddingVertical: Spacing.two, borderBottomWidth: 1 },
  crop: { width: 84, height: 56, borderRadius: 6 },
  rowBody: { flex: 1, gap: 2 },
  rowTitle: { fontSize: 15, fontWeight: '600' },
  rowMeta: { fontSize: 13 },
  rowFooter: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two, marginTop: 2 },
});
