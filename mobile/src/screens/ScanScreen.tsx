import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import React, { useRef, useState } from 'react';
import { Image, Modal, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useScreenInsets } from '../hooks/useScreenInsets';

import { endpoints } from '../api/endpoints';
import { Test } from '../api/types';
import { invalidate, useApi } from '../hooks/useApi';
import { prepareSheetForUpload } from '../lib/prepareSheet';
import { radius, spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import ScanIcon from '../ui/icons/ScanIcon';
import {
  Badge, Button, Card, EmptyState, ErrorState, Loading, Notice, Txt, useToast,
} from '../ui';

export default function ScanScreen({ route, navigation }: any) {
  const preselected: number | undefined = route.params?.testId;
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const screen = useScreenInsets();
  const toast = useToast();

  const { data, error, loading, reload } = useApi(() => endpoints.listTests(), [], { key: 'tests' });
  const [testId, setTestId] = useState<number | null>(preselected ?? null);
  const [image, setImage] = useState<{ uri: string; name: string } | null>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);

  if (loading && !data) return <Loading text="Loading tests…" />;
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;

  // Only a test with a stored answer key can be scanned against; offering the
  // others would just produce a 409 from the server.
  const scannable = (data?.tests ?? []).filter((t) => (t.key_count ?? 0) > 0);
  const test = scannable.find((t) => t.id === testId) ?? null;

  if (scannable.length === 0) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.background }}>
        <EmptyState
          icon="⚑"
          title="No test is ready to scan"
          body="A sheet is scored against a stored answer key, so a test needs its key before you can scan for it."
          action={
            <Button title="Go to Tests" onPress={() => navigation.navigate('Tests')} />
          }
        />
      </View>
    );
  }

  const openCamera = async () => {
    if (!permission?.granted) {
      const res = await requestPermission();
      if (!res.granted) {
        toast.show('Camera permission is needed to photograph a sheet.', 'error');
        return;
      }
    }
    setCameraOpen(true);
  };

  const capture = async () => {
    try {
      const photo = await cameraRef.current?.takePictureAsync({ quality: 0.85 });
      if (photo?.uri) {
        setImage({ uri: photo.uri, name: 'sheet.jpg' });
        setFailure(null);
      }
    } catch (err) {
      toast.show(`Could not take the photo: ${(err as Error).message}`, 'error');
    } finally {
      setCameraOpen(false);
    }
  };

  const pick = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.9,
    });
    if (!res.canceled && res.assets[0]) {
      const a = res.assets[0];
      setImage({ uri: a.uri, name: a.fileName || 'sheet.jpg' });
      setFailure(null);
    }
  };

  const submit = async () => {
    if (!test || !image) return;
    setFailure(null);
    setUploading(true);
    // Each stage is reported separately: a failure here used to surface as one
    // vague message, which made it impossible to tell a resize crash from a
    // refused upload from a server error.
    let stage = 'preparing the image';
    let prepared: Awaited<ReturnType<typeof prepareSheetForUpload>> | null = null;
    try {
      // Downscale before upload: a raw phone photo is several megabytes, and
      // the engine discards everything above 1600px wide anyway. Returns the
      // name and type that match the bytes actually produced.
      prepared = await prepareSheetForUpload(image.uri, image.name);

      stage = 'contacting the server';
      // Confirms the address is reachable before the long upload, so a wrong
      // API address is reported as such instead of as a failed upload.
      await endpoints.health();

      stage = 'uploading the sheet';
      const result = await endpoints.scan(test.id, prepared);
      // A new submission changes history, the dashboard counts and the
      // test's own result list.
      invalidate('results');
      invalidate('dashboard');
      invalidate(`test:${test.id}`);
      invalidate('tests');
      toast.show(
        `Read ${result.answered} answers · ${result.score.total}/${result.score.max} marks.`,
        'success',
      );
      setImage(null);
      // Straight to the review screen, where OCR data is corrected and the
      // report is generated.
      navigation.navigate('Result', {
        submissionId: result.submission_id,
        justScanned: true,
      });
    } catch (err) {
      const e = err as { message?: string; status?: number };
      // The prepared file's own shape is folded into the message during this
      // investigation: a native-only upload failure with no further detail
      // gives no way to tell a bad URI from a missing content-type from
      // something else, and that shape is exactly what decides which.
      const shape = prepared
        ? ` [uri=${prepared.uri.slice(0, 60)}${prepared.uri.length > 60 ? '…' : ''}, name=${prepared.name}, type=${prepared.type}]`
        : ' [prepared image unavailable]';
      setFailure(
        `Failed while ${stage}: ${e?.message || String(err)}` +
          (e?.status ? ` (HTTP ${e.status})` : '') +
          (stage === 'uploading the sheet' ? shape : ''),
      );
    } finally {
      setUploading(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <ScrollView
        contentContainerStyle={{
          padding: spacing.lg,
          paddingTop: screen.top,
          paddingBottom: screen.scrollBottom,
        }}
      >
        <Txt variant="display" weight="bold">Scan sheet</Txt>
        <Txt variant="small" muted style={{ marginTop: 2, marginBottom: spacing.lg }}>
          Pick the test, add a photo of the sheet, then evaluate.
        </Txt>

        {/* 1. test */}
        <Card style={{ marginBottom: spacing.lg }}>
          <Txt variant="caption" muted weight="bold">STEP 1</Txt>
          <Txt variant="heading" weight="bold" style={{ marginTop: 2, marginBottom: spacing.md }}>
            Which test?
          </Txt>
          <View style={{ gap: spacing.sm }}>
            {scannable.map((t) => (
              <TestOption key={t.id} test={t} selected={t.id === testId}
                          onPress={() => setTestId(t.id)} />
            ))}
          </View>
        </Card>

        {/* 2. image */}
        <Card style={{ marginBottom: spacing.lg }}>
          <Txt variant="caption" muted weight="bold">STEP 2</Txt>
          <Txt variant="heading" weight="bold" style={{ marginTop: 2, marginBottom: spacing.md }}>
            The answer sheet
          </Txt>

          {image ? (
            <>
              <Image
                source={{ uri: image.uri }}
                style={{
                  width: '100%', aspectRatio: 0.7, borderRadius: radius.md,
                  borderWidth: 1.5, borderColor: colors.border,
                  backgroundColor: colors.muted,
                }}
                resizeMode="contain"
              />
              <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md }}>
                <Button title="Retake" variant="outline" size="sm"
                        onPress={openCamera} disabled={uploading} style={{ flex: 1 }} />
                <Button title="Choose another" variant="outline" size="sm"
                        onPress={pick} disabled={uploading} style={{ flex: 1 }} />
              </View>
            </>
          ) : (
            <>
              <Notice
                tone="info"
                title="For a clean read"
                body="Lay the sheet flat, fill the frame with the whole answer grid, and keep the light even — no shadow across the bubbles."
              />
              <Button
                title="Take a photo"
                icon={<ScanIcon size={18} color={colors.primaryForeground}
                                documentColor="#FFFFFF" lineColor={colors.primary} />}
                onPress={openCamera} fullWidth
              />
              <Button title="Upload from gallery" variant="outline" onPress={pick}
                      fullWidth style={{ marginTop: spacing.sm }} />
            </>
          )}
        </Card>

        {!!failure && (
          <Notice tone="danger" title="The sheet could not be evaluated" body={failure} />
        )}

        <Button
          title={uploading ? 'Evaluating…' : 'Evaluate sheet'}
          onPress={submit}
          loading={uploading}
          disabled={!test || !image}
          fullWidth
        />
        {(!test || !image) && (
          <Txt variant="caption" muted center style={{ marginTop: spacing.sm }}>
            {!test ? 'Choose a test' : 'Add a photo of the sheet'} to continue.
          </Txt>
        )}
        {uploading && (
          <Txt variant="caption" muted center style={{ marginTop: spacing.sm }}>
            Reading bubbles, extracting candidate details and scoring against the
            stored answer key. This takes a few seconds.
          </Txt>
        )}
      </ScrollView>

      <Modal visible={cameraOpen} animationType="slide"
             onRequestClose={() => setCameraOpen(false)}>
        <View style={{ flex: 1, backgroundColor: '#000' }}>
          <CameraView ref={cameraRef} style={{ flex: 1 }} facing="back" />
          {/* CameraView (SDK 57) no longer renders children -- the framing
              guide is laid over it as an absolutely positioned sibling
              instead, matching the library's own recommendation. */}
          <View
            pointerEvents="none"
            style={{
              position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
              padding: spacing.xl, paddingTop: insets.top + spacing.xl,
            }}
          >
            <View
              style={{
                flex: 1, borderWidth: 2, borderColor: 'rgba(255,255,255,0.7)',
                borderRadius: radius.md, borderStyle: 'dashed',
              }}
            />
            <Txt variant="small" center color="#FFF" style={{ marginTop: spacing.md }}>
              Fit the entire answer grid inside the frame
            </Txt>
          </View>
          <View
            style={{
              padding: spacing.lg, paddingBottom: insets.bottom + spacing.lg,
              backgroundColor: '#000', flexDirection: 'row',
              alignItems: 'center', gap: spacing.md,
            }}
          >
            <Button title="Cancel" variant="ghost"
                    onPress={() => setCameraOpen(false)} style={{ flex: 1 }} />
            <Pressable
              onPress={capture}
              accessibilityRole="button"
              accessibilityLabel="Take photo"
              style={{
                width: 72, height: 72, borderRadius: radius.pill,
                backgroundColor: '#FFF', borderWidth: 5, borderColor: colors.primary,
              }}
            />
            <View style={{ flex: 1 }} />
          </View>
        </View>
      </Modal>
    </View>
  );
}

function TestOptionBase({
  test, selected, onPress,
}: { test: Test; selected: boolean; onPress: () => void }) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      style={{
        borderWidth: 1.5,
        borderColor: selected ? colors.primary : colors.border,
        backgroundColor: selected ? `${colors.primary}14` : colors.card,
        borderRadius: radius.md,
        padding: spacing.md,
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.md,
      }}
    >
      <View
        style={{
          width: 20, height: 20, borderRadius: radius.pill, borderWidth: 2,
          borderColor: selected ? colors.primary : colors.input,
          alignItems: 'center', justifyContent: 'center',
        }}
      >
        {selected && (
          <View style={{ width: 10, height: 10, borderRadius: radius.pill, backgroundColor: colors.primary }} />
        )}
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Txt weight="semibold" numberOfLines={1}>{test.name}</Txt>
        <Txt variant="caption" muted numberOfLines={1} style={{ marginTop: 2 }}>
          {test.layout.toUpperCase()} · {test.key_count} answers in key
        </Txt>
      </View>
      <Badge label={test.layout} tone="info" small />
    </Pressable>
  );
}

// Memoised: a long list re-renders every row whenever the screen's own
// state changes, and these rows are pure functions of their props.
const TestOption = React.memo(TestOptionBase);
