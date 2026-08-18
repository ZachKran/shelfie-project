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
import { Accent, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

/**
 * The review queue. One book at a time, because the decision is per book and a
 * long scrolling list invites bulk-accepting things the model got wrong.
 *
 * There are exactly two ways to save: pick a catalog entry, or type the book
 * yourself. Each has its own button, so choosing one never quietly undoes the
 * other. Every item leaves this screen through an explicit choice, and an
 * unfinished queue stays reachable from Your scans.
 */
export default function ReviewScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const theme = useTheme();

  const [scan, setScan] = useState<Scan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cursor, setCursor] = useState(0);
  const [busy, setBusy] = useState<'catalog' | 'manual' | 'discard' | null>(null);
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

  async function save(kind: 'catalog' | 'manual' | 'discard') {
    if (!item) return;
    setBusy(kind);
    setError(null);
    try {
      if (kind === 'discard') {
        await resolveItem(item.id, 'discard');
        setNotice(null);
      } else if (kind === 'catalog' && selected) {
        // "confirm" when the user agrees with the matcher, "correct" when they
        // picked something else. The distinction is recorded on the book.
        const action = selected === item.match_id ? 'confirm' : 'correct';
        const result = await resolveItem(item.id, action, { catalog_id: selected });
        setNotice(
          result.already_in_library
            ? `${result.book?.title} was already in your library.`
            : `Saved ${result.book?.title}.`
        );
      } else if (kind === 'manual') {
        const result = await resolveItem(item.id, 'correct', {
          title: manualTitle.trim(),
          author: manualAuthor.trim(),
        });
        setNotice(
          result.already_in_library
            ? `${result.book?.title} was already in your library.`
            : `Saved ${result.book?.title}.`
        );
      }
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
      setBusy(null);
    }
  }

  if (error && !scan) return <ErrorState message={error} onRetry={load} />;
  if (!scan) return <Loading label="Loading review queue..." />;

  if (!item) {
    return (
      <EmptyState
        title="Review complete"
        body="Every book from this scan has been saved or discarded."
        action={
          <>
            <Button label="See my library" onPress={() => router.push('/library')} />
            <Button label="Your scans" variant="secondary" onPress={() => router.push('/scans')} />
          </>
        }
      />
    );
  }

  const meta = STATUS_META[item.status];
  const selectedCandidate =
    [...item.candidates, ...results].find((c) => c.id === selected) ?? null;

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
            <Text style={[styles.readTitle, { color: theme.text }]}>
              {item.read_title || '(no title)'}
            </Text>
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

      {/* --- Path one: pick a book from the catalog --- */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: theme.text }]}>
          {item.candidates.length > 0 ? 'Pick from the catalog' : 'Search the catalog'}
        </Text>

        {item.candidates.map((candidate) => (
          <CandidateRow
            key={candidate.id}
            candidate={candidate}
            selected={selected === candidate.id}
            onPress={() => setSelected(candidate.id)}
          />
        ))}

        <TextInput
          value={query}
          onChangeText={runSearch}
          placeholder="Search by title or author"
          placeholderTextColor={theme.textSecondary}
          style={[
            styles.input,
            { color: theme.text, backgroundColor: theme.backgroundElement },
          ]}
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

        <Button
          label={
            selectedCandidate
              ? `Save "${selectedCandidate.title}"`
              : 'Select a book above to save it'
          }
          onPress={() => save('catalog')}
          busy={busy === 'catalog'}
          disabled={!selected}
        />
      </View>

      {/* --- Path two: type it yourself --- */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: theme.text }]}>
          Not in the catalog? Type it yourself
        </Text>
        <TextInput
          value={manualTitle}
          onChangeText={setManualTitle}
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
        <Button
          label="Save what I typed"
          onPress={() => save('manual')}
          busy={busy === 'manual'}
          disabled={!manualTitle.trim()}
        />
      </View>

      {notice ? <Text style={[styles.notice, { color: theme.textSecondary }]}>{notice}</Text> : null}
      {error ? <Text style={styles.inlineError}>{error}</Text> : null}

      <View style={styles.section}>
        <Button
          label="Not a book, discard"
          variant="danger"
          onPress={() => save('discard')}
          busy={busy === 'discard'}
        />
        {queue.length > 1 ? (
          <Button
            label="Skip this one"
            variant="secondary"
            onPress={() => setCursor((c) => (c + 1) % queue.length)}
          />
        ) : null}
      </View>

      {/* Leaving is a first-class action. Whatever is left stays in the queue
          and is reachable again from Your scans. */}
      <View style={styles.exit}>
        <Text style={[styles.exitNote, { color: theme.textSecondary }]}>
          {queue.length} {queue.length === 1 ? 'book is' : 'books are'} still waiting. They
          will be here when you come back.
        </Text>
        <Button label="Finish later" variant="secondary" onPress={() => router.push('/scans')} />
        <Button label="My library" variant="secondary" onPress={() => router.push('/library')} />
        <Button label="Scan another shelf" variant="secondary" onPress={() => router.replace('/')} />
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
          borderColor: selected ? Accent.primary : 'transparent',
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
  container: { padding: Spacing.three, gap: Spacing.four, maxWidth: 640, width: '100%', alignSelf: 'center' },
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
  exit: { gap: Spacing.two, marginTop: Spacing.two, paddingTop: Spacing.three, borderTopWidth: 1, borderTopColor: Accent.border },
  exitNote: { fontSize: 13, textAlign: 'center' },
  notice: { fontSize: 14 },
  inlineError: { color: Accent.danger, fontSize: 14 },
});
