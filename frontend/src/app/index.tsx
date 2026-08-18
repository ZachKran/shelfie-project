import * as ImagePicker from 'expo-image-picker';
import { router } from 'expo-router';
import { useState } from 'react';
import { Image, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError, BASE_URL, uploadScan } from '@/api/client';
import { Button, Card, ErrorState } from '@/components/ui-kit';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export default function CaptureScreen() {
  const theme = useTheme();
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pick(useCamera: boolean) {
    setError(null);
    const permission = useCamera
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError(
        useCamera
          ? 'Camera access was denied. You can still choose a photo from your library.'
          : 'Photo library access was denied.'
      );
      return;
    }

    const result = useCamera
      ? await ImagePicker.launchCameraAsync({ quality: 0.9 })
      : await ImagePicker.launchImageLibraryAsync({ quality: 0.9 });
    if (result.canceled || !result.assets?.length) return;

    const asset = result.assets[0];
    setPreview(asset.uri);
    await upload(asset.uri, asset.fileName ?? 'shelf.jpg');
  }

  async function upload(uri: string, name: string) {
    setBusy(true);
    setError(null);
    try {
      const scan = await uploadScan(uri, name);
      router.push({ pathname: '/scan/[id]', params: { id: String(scan.id) } });
    } catch (err) {
      // The photo stays on screen so a retry does not mean taking it again.
      setError(err instanceof ApiError ? err.message : 'The scan could not be uploaded.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={[styles.title, { color: theme.text }]}>Scan a bookshelf</Text>
      <Text style={[styles.body, { color: theme.textSecondary }]}>
        Take a photo of a shelf and Shelfie will pull out the individual books, read the
        spines, and match them against the catalog. Anything it is unsure about comes to
        you before it is saved.
      </Text>

      {preview ? <Image source={{ uri: preview }} style={styles.preview} resizeMode="cover" /> : null}

      <View style={styles.actions}>
        <Button label="Take a photo" onPress={() => pick(true)} busy={busy} />
        <Button label="Choose from library" variant="secondary" onPress={() => pick(false)} busy={busy} />
      </View>

      {busy ? (
        <Text style={[styles.hint, { color: theme.textSecondary }]}>
          Detecting spines and reading them. A full shelf takes a little while.
        </Text>
      ) : null}

      {error ? (
        <Card>
          <ErrorState
            message={error}
            onRetry={preview ? () => upload(preview, 'shelf.jpg') : undefined}
          />
        </Card>
      ) : null}

      <View style={styles.footer}>
        <Button
          label="Scans to review"
          variant="secondary"
          onPress={() => router.push('/scans')}
        />
        <Button label="My library" variant="secondary" onPress={() => router.push('/library')} />
        <Text style={[styles.hint, { color: theme.textSecondary }]}>Server: {BASE_URL}</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: Spacing.four, gap: Spacing.three, maxWidth: 640, width: '100%', alignSelf: 'center' },
  title: { fontSize: 26, fontWeight: '700' },
  body: { fontSize: 15, lineHeight: 21 },
  preview: { width: '100%', height: 260, borderRadius: 12 },
  actions: { gap: Spacing.two },
  footer: { marginTop: Spacing.four, gap: Spacing.two },
  hint: { fontSize: 13, textAlign: 'center' },
});
