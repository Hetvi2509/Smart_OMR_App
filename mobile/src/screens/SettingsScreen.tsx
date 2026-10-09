import React, { useState } from 'react';
import { ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useScreenInsets } from '../hooks/useScreenInsets';

import { getBaseUrl, guessBaseUrl, setBaseUrl } from '../api/client';
import { endpoints } from '../api/endpoints';
import { Health } from '../api/types';
import { useAuth } from '../store/auth';
import { spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import {
  Badge, Button, Card, Dialog, Field, Notice, Row, SectionHeader, Segmented,
  Txt, useToast,
} from '../ui';

export default function SettingsScreen() {
  const { colors, mode, setMode } = useTheme();
  const insets = useSafeAreaInsets();
  const screen = useScreenInsets();
  const { user, signOut } = useAuth();
  const toast = useToast();

  const [url, setUrl] = useState(getBaseUrl());
  const [health, setHealth] = useState<Health | null>(null);
  const [checking, setChecking] = useState(false);
  const [confirmOut, setConfirmOut] = useState(false);

  const check = async () => {
    setChecking(true);
    try {
      await setBaseUrl(url);
      setUrl(getBaseUrl());
      const h = await endpoints.health();
      setHealth(h);
      toast.show(
        h.database === 'connected'
          ? 'Connected. Database reachable.'
          : 'Server answered, but the database is unreachable.',
        h.database === 'connected' ? 'success' : 'error',
      );
    } catch (err) {
      setHealth(null);
      toast.show((err as Error).message, 'error');
    } finally {
      setChecking(false);
    }
  };

  const reset = async () => {
    const guessed = guessBaseUrl();
    await setBaseUrl(guessed);
    setUrl(getBaseUrl());
    toast.show('Reset to the detected address.', 'info');
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.background }}
      contentContainerStyle={{
        padding: spacing.lg,
        paddingTop: screen.top,
        paddingBottom: screen.scrollBottom,
      }}
      keyboardShouldPersistTaps="handled"
    >
      <Txt variant="display" weight="bold">Profile</Txt>
      <Txt variant="small" muted style={{ marginTop: 2, marginBottom: spacing.lg }}>
        Account, server and appearance.
      </Txt>

      <Card style={{ marginBottom: spacing.xl }}>
        <Txt variant="heading" weight="bold">{user?.full_name}</Txt>
        <Txt variant="small" muted style={{ marginTop: 2 }}>{user?.email}</Txt>
        {!!user?.institution_name && (
          <Txt variant="small" muted style={{ marginTop: 2 }}>
            {user.institution_name}
          </Txt>
        )}
        <View style={{ marginTop: spacing.md }}>
          <Badge label={user?.role || 'user'} tone="info" />
        </View>
      </Card>

      <SectionHeader title="Appearance" />
      <Card style={{ marginBottom: spacing.xl }}>
        <Segmented
          label="Theme"
          options={[
            { value: 'system', label: 'System' },
            { value: 'light', label: 'Light' },
            { value: 'dark', label: 'Dark' },
          ]}
          value={mode}
          onChange={(v) => setMode(v as typeof mode)}
        />
      </Card>

      <SectionHeader
        title="Server"
        subtitle="Where the app sends scans and reads results"
      />
      <Card style={{ marginBottom: spacing.xl }}>
        <Notice
          tone="info"
          title="Your phone and computer must share a network"
          body="The address is detected from the Expo dev server. Change it only if the backend runs elsewhere."
        />
        <Field
          label="API address"
          value={url}
          onChangeText={setUrl}
          placeholder="http://192.168.1.5:8000"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          hint="A bare IP works too — the scheme and port are filled in."
          editable={!checking}
        />
        <View style={{ flexDirection: 'row', gap: spacing.sm }}>
          <Button title="Save and test" onPress={check} loading={checking}
                  style={{ flex: 1 }} />
          <Button title="Auto-detect" variant="outline" onPress={reset}
                  disabled={checking} />
        </View>

        {!!health && (
          <View style={{ marginTop: spacing.lg }}>
            <Row label="Server" value={health.status} tone={colors.success} />
            <Row label="Database"
                 value={health.database}
                 tone={health.database === 'connected' ? colors.success : colors.destructive} />
            <Row label="Candidate OCR"
                 value={health.ocr_available ? 'available' : 'unavailable'}
                 tone={health.ocr_available ? colors.success : colors.accent} />
            <Row label="API version" value={health.version} last />
            {!health.ocr_available && (
              <Txt variant="caption" muted style={{ marginTop: spacing.sm }}>
                Sheets will still be read and scored; candidate details must be
                typed in on the result screen.
              </Txt>
            )}
          </View>
        )}
      </Card>

      <SectionHeader title="About" />
      <Card padded={false} style={{ padding: spacing.md, marginBottom: spacing.xl }}>
        <Row label="Application" value="Smart OMR Evaluator" />
        <Row label="Version" value="1.0.0" />
        <Row label="Theme" value="poppy-1" />
        <Row label="Data" value="Neon PostgreSQL" last />
      </Card>

      <Button title="Sign out" variant="destructive"
              onPress={() => setConfirmOut(true)} fullWidth />

      <Dialog
        visible={confirmOut}
        title="Sign out?"
        message="You will need your email and password to sign back in."
        confirmLabel="Sign out"
        destructive
        onConfirm={() => { setConfirmOut(false); signOut(); }}
        onCancel={() => setConfirmOut(false)}
      />
    </ScrollView>
  );
}
