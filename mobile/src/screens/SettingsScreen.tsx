import React, { useState } from 'react';
import { ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useScreenInsets } from '../hooks/useScreenInsets';

import { useAuth } from '../store/auth';
import { spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import {
  Badge, Button, Card, Dialog, Row, SectionHeader, Segmented, Txt,
} from '../ui';

export default function SettingsScreen() {
  const { colors, mode, setMode } = useTheme();
  const insets = useSafeAreaInsets();
  const screen = useScreenInsets();
  const { user, signOut } = useAuth();

  const [confirmOut, setConfirmOut] = useState(false);

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
        Account and appearance.
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

      <SectionHeader title="About" />
      <Card padded={false} style={{ padding: spacing.md, marginBottom: spacing.xl }}>
        <Row label="Application" value="Smart OMR Evaluator" />
        <Row label="Version" value="1.0.0" last />
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
