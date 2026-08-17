import { router } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import { getLibrary, removeBook, type LibraryBook } from '@/api/client';
import { Button, EmptyState, ErrorState, Loading } from '@/components/ui-kit';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export default function LibraryScreen() {
  const theme = useTheme();
  const [books, setBooks] = useState<LibraryBook[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setBooks(await getLibrary());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load your library.');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function remove(id: number) {
    const previous = books;
    setBooks((current) => current?.filter((b) => b.id !== id) ?? null);
    try {
      await removeBook(id);
    } catch {
      setBooks(previous ?? null);
      setError('That book could not be removed.');
    }
  }

  if (error && !books) return <ErrorState message={error} onRetry={load} />;
  if (!books) return <Loading label="Loading your library..." />;

  if (books.length === 0) {
    return (
      <EmptyState
        title="No books yet"
        body="Scan a shelf and confirm the books you want to keep. They will show up here."
        action={<Button label="Scan a shelf" onPress={() => router.replace('/')} />}
      />
    );
  }

  return (
    <FlatList
      contentContainerStyle={styles.container}
      data={books}
      keyExtractor={(book) => String(book.id)}
      ListHeaderComponent={
        <Text style={[styles.count, { color: theme.textSecondary }]}>
          {books.length} {books.length === 1 ? 'book' : 'books'}
        </Text>
      }
      renderItem={({ item }) => (
        <View style={[styles.row, { borderBottomColor: theme.backgroundElement }]}>
          <View style={styles.rowBody}>
            <Text style={[styles.title, { color: theme.text }]}>{item.title}</Text>
            <Text style={[styles.meta, { color: theme.textSecondary }]}>
              {item.author || 'Unknown author'}
              {item.manually_entered ? ' · added by hand' : ''}
            </Text>
          </View>
          <Pressable onPress={() => remove(item.id)} accessibilityRole="button">
            <Text style={styles.remove}>Remove</Text>
          </Pressable>
        </View>
      )}
      ListFooterComponent={
        error ? <Text style={styles.inlineError}>{error}</Text> : null
      }
    />
  );
}

const styles = StyleSheet.create({
  container: { padding: Spacing.three, maxWidth: 640, width: '100%', alignSelf: 'center' },
  count: { fontSize: 13, marginBottom: Spacing.two },
  row: { flexDirection: 'row', alignItems: 'center', gap: Spacing.three, paddingVertical: Spacing.three, borderBottomWidth: 1 },
  rowBody: { flex: 1, gap: 2 },
  title: { fontSize: 15, fontWeight: '600' },
  meta: { fontSize: 13 },
  remove: { color: '#B91C1C', fontSize: 14, fontWeight: '600' },
  inlineError: { color: '#B91C1C', fontSize: 14, marginTop: Spacing.three },
});
