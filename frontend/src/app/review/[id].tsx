import { router, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  getScan,
  mediaUrl,
  resolveItem,
  searchCatalog,
  type Candidate,
  type Scan,
} from '@/api/client';
import { Button, Card, EmptyState, ErrorState, Loading, Pill } from '@/components/ui-kit';
import { STATUS_META } from '@/constants/status';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

/**
 * The review queue. One book at a time, because the decision is per book and a
 * long scrolling list invites bulk-accepting things the model got wrong.
 *
 * Every item leaves this screen through an explicit choice: confirm, correct,
 * or discard. Nothing is auto-accepted and nothing is dropped on the floor.
 */
export default function ReviewScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const theme = useTheme();

  const [scan, setScan] = useState<Scan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cursor, setCursor] = useState(0);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Candidate[]>([]);
  const [manualTitle, setManualTitle] = useState('');
  const [manualAuthor, setManualAuthor] = useState('');
  const [notice, setNotice] = useState<string | null>(null);

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

  const queue = useMemo(
    () => (scan?.items ?? []).filter((i) => STATUS_META[i.status].needsReview && !i.resolved),
    [scan]
  );
  const item = queue[cursor];

  useEffect(() => {
    // Reset the per-item working state whenever the queue moves on.
    setSelected(item?.match_id || item?.candidates[0]?.id || null);
    setQuery('');
    setResults([]);
    setManualTitle(item?.read_title ?? '');
    setManualAuthor(item?.read_author ?? '');
  }, [item?.id]);

  async function runSearch(text: string) {
    setQuery(text);
    if (text.trim().length < 2) {
      setResults([]);
      return;
    }
    try {
      const { results: found } = await searchCatalog(text);
      setResults(found);
    } catch {
      setResults([]);
    }
  }

  async function act(action: 'confirm' | 'correct' | 'discard') {
    if (!item) return;
    setBusy(true);
    setError(null);
    try {
      const payload =
        action === 'correct'
          ? selected
            ? { catalog_id: selected }
            : { title: manualTitle.trim(), author: manualAuthor.trim() }
          : {};
      const result = await resolveItem(item.id, action, payload);
      if (result.already_in_library) {
        setNotice(`${result.book?.title} was already in your library.`);
      } else {
        setNotice(null);
      }
      // Advance locally so the queue does not jump around under the user.
      setScan((prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.map((i) => (i.id === item.id ? { ...i, resolved: true } : i)),
            }
          : prev
      );
      setCursor((c) => Math.min(c, Math.max(queue.length - 2, 0)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That did not save. Try again.');
    } finally {
      setBusy(false);
    }
  }

  if (error && !scan) return <ErrorState message={error} onRetry={load} />;
  if (!scan) return <Loading label="Loading review queue..." />;

  if (!item) {
    return (
      <EmptyState
        title="Review complete"
        body="Every book from this scan has been confirmed, corrected, or discarded."
        action={
          <>
            <Button label="See my library" onPress={() => router.push('/library')} />
            <Button label="Scan another shelf" variant="secondary" onPress={() => router.replace('/')} />
          </>
        }
      />
    );
  }

  const meta = STATUS_META[item.status];
  const canConfirm = item.status === 'review' && !!item.match_id;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={[styles.progress, { color: theme.textSecondary }]}>
        {cursor + 1} of {queue.length} to review
      </Text>

      {item.crop_url ? (
        <Image source={{ uri: mediaUrl(item.crop_url) }} style={styles.crop} resizeMode="contain" />
      ) : null}

      <Card>
        <Pill label={meta.label} color={meta.color} />
        <Text style={[styles.readLabel, { color: theme.textSecondary }]}>Read from the spine</Text>
        {item.read_title || item.read_author ? (
          <>
            <Text style={[styles.readTitle, { color: theme.text }]}>{item.read_title || '(no title)'}</Text>
            <Text style={[styles.readAuthor, { color: theme.textSecondary }]}>
              {item.read_author || '(no author)'}
            </Text>
          </>
        ) : (
          <Text style={[styles.readAuthor, { color: theme.textSecondary }]}>
            {item.read_error || 'This spine could not be read.'}
          </Text>
        )}
      </Card>

      {item.candidates.length > 0 ? (
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: theme.text }]}>Catalog matches</Text>
          {item.candidates.map((candidate) => (
            <CandidateRow
              key={candidate.id}
              candidate={candidate}
              selected={selected === candidate.id}
              onPress={() => setSelected(candidate.id)}
            />
          ))}
        </View>
      ) : null}

      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: theme.text }]}>Search the catalog</Text>
        <TextInput
          value={query}
          onChangeText={runSearch}
          placeholder="Title or author"
          placeholderTextColor={theme.textSecondary}
          style={[styles.input, { color: theme.text, backgroundColor: theme.backgroundElement }]}
          autoCorrect={false}
        />
        {results.map((candidate) => (
          <CandidateRow
            key={`search-${candidate.id}`}
            candidate={candidate}
            selected={selected === candidate.id}
            onPress={() => setSelected(candidate.id)}
          />
        ))}
      </View>

      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: theme.text }]}>Or type it yourself</Text>
        <TextInput
          value={manualTitle}
          onChangeText={(text) => {
            setManualTitle(text);
            setSelected(null);
          }}
          placeholder="Title"
          placeholderTextColor={theme.textSecondary}
          style={[styles.input, { color: theme.text, backgroundColor: theme.backgroundElement }]}
        />
        <TextInput
          value={manualAuthor}
          onChangeText={setManualAuthor}
          placeholder="Author"
          placeholderTextColor={theme.textSecondary}
          style={[styles.input, { color: theme.text, backgroundColor: theme.backgroundElement }]}
        />
      </View>

      {notice ? <Text style={[styles.notice, { color: theme.textSecondary }]}>{notice}</Text> : null}
      {error ? <Text style={styles.inlineError}>{error}</Text> : null}

      <View style={styles.actions}>
        {canConfirm ? (
          <Button label="Confirm this match" onPress={() => act('confirm')} busy={busy} />
        ) : null}
        <Button
          label="Save selection"
          variant={canConfirm ? 'secondary' : 'primary'}
          onPress={() => act('correct')}
          busy={busy}
          disabled={!selected && !manualTitle.trim()}
        />
        <Button label="Not a book, discard" variant="danger" onPress={() => act('discard')} busy={busy} />
        {queue.length > 1 ? (
          <Button
            label="Skip for now"
            variant="secondary"
            onPress={() => setCursor((c) => (c + 1) % queue.length)}
          />
        ) : null}
      </View>
    </ScrollView>
  );
}

function CandidateRow({
  candidate,
  selected,
  onPress,
}: {
  candidate: Candidate;
  selected: boolean;
  onPress: () => void;
}) {
  const theme = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={[
        styles.candidate,
        {
          backgroundColor: selected ? theme.backgroundSelected : theme.backgroundElement,
          borderColor: selected ? '#2563EB' : 'transparent',
        },
      ]}>
      <View style={styles.candidateBody}>
        <Text style={[styles.candidateTitle, { color: theme.text }]}>{candidate.title}</Text>
        <Text style={[styles.candidateMeta, { color: theme.textSecondary }]}>
          {candidate.author}
          {candidate.year ? ` · ${candidate.year}` : ''}
          {candidate.publisher ? ` · ${candidate.publisher}` : ''}
        </Text>
      </View>
      <Text style={[styles.candidateMeta, { color: theme.textSecondary }]}>
        {(candidate.score * 100).toFixed(0)}%
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { padding: Spacing.three, gap: Spacing.three, maxWidth: 640, width: '100%', alignSelf: 'center' },
  progress: { fontSize: 13, textAlign: 'center' },
  crop: { width: '100%', height: 130, borderRadius: 8 },
  readLabel: { fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.5 },
  readTitle: { fontSize: 18, fontWeight: '700' },
  readAuthor: { fontSize: 15 },
  section: { gap: Spacing.two },
  sectionTitle: { fontSize: 15, fontWeight: '700' },
  input: { borderRadius: 8, paddingHorizontal: Spacing.three, paddingVertical: 12, fontSize: 15 },
  candidate: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    borderRadius: 8,
    borderWidth: 2,
    padding: Spacing.three,
  },
  candidateBody: { flex: 1 },
  candidateTitle: { fontSize: 15, fontWeight: '600' },
  candidateMeta: { fontSize: 13 },
  actions: { gap: Spacing.two, marginTop: Spacing.two },
  notice: { fontSize: 14 },
  inlineError: { color: '#B91C1C', fontSize: 14 },
});
