import React, { useState } from 'react';
import {
  KeyboardAvoidingView, Platform, Pressable, ScrollView, View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { endpoints } from '../api/endpoints';
import { getBaseUrl } from '../api/client';
import { useAuth } from '../store/auth';
import { radius, spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import { Button, Card, Field, Notice, Txt, useToast } from '../ui';

export default function LoginScreen({ navigation }: any) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { signIn } = useAuth();
  const toast = useToast();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    if (!email.trim() || !password) {
      setError('Enter your email and password.');
      return;
    }
    setBusy(true);
    try {
      await signIn(email, password);
      toast.show('Signed in.', 'success');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const checkServer = async () => {
    try {
      const h = await endpoints.health();
      toast.show(`Server reachable — database ${h.database}.`,
                 h.database === 'connected' ? 'success' : 'error');
    } catch (err) {
      toast.show((err as Error).message, 'error');
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.background }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        contentContainerStyle={{
          padding: spacing.lg,
          paddingTop: insets.top + spacing.xxl,
          paddingBottom: insets.bottom + spacing.xl,
          flexGrow: 1,
          justifyContent: 'center',
        }}
        keyboardShouldPersistTaps="handled"
      >
        <View style={{ alignItems: 'center', marginBottom: spacing.xl }}>
          <View
            style={{
              width: 66, height: 66, borderRadius: radius.lg,
              backgroundColor: colors.primary, alignItems: 'center',
              justifyContent: 'center', borderWidth: 1.5,
              borderColor: colors.border, marginBottom: spacing.md,
            }}
          >
            <Txt variant="title" weight="bold" color={colors.primaryForeground}>
              ◉
            </Txt>
          </View>
          <Txt variant="display" weight="bold" center>Smart OMR</Txt>
          <Txt variant="small" muted center style={{ marginTop: 4 }}>
            Examination evaluation for institutes
          </Txt>
        </View>

        <Card>
          <Txt variant="heading" weight="bold">Sign in</Txt>
          <Txt variant="small" muted style={{ marginTop: 4, marginBottom: spacing.lg }}>
            Use your institute account to continue.
          </Txt>

          {!!error && <Notice tone="danger" title="Could not sign in" body={error} />}

          <Field
            label="Email"
            required
            value={email}
            onChangeText={setEmail}
            placeholder="teacher@institute.edu"
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            editable={!busy}
          />
          <Field
            label="Password"
            required
            value={password}
            onChangeText={setPassword}
            placeholder="Your password"
            secureTextEntry
            autoComplete="password"
            editable={!busy}
            onSubmitEditing={submit}
            returnKeyType="go"
          />

          <Button title="Sign in" onPress={submit} loading={busy} fullWidth />

          <Pressable
            onPress={() => navigation.navigate('SignUp')}
            style={{ marginTop: spacing.lg, alignItems: 'center' }}
            disabled={busy}
          >
            <Txt variant="small" muted>
              No account yet?{' '}
              <Txt variant="small" weight="bold" color={colors.primary}>
                Create one
              </Txt>
            </Txt>
          </Pressable>
        </Card>

        {/* The commonest setup failure is the API address, so it is visible and
            testable from the first screen rather than buried in Settings. */}
        <Pressable onPress={checkServer} style={{ marginTop: spacing.lg, alignItems: 'center' }}>
          <Txt variant="caption" muted center>
            API: {getBaseUrl()}
          </Txt>
          <Txt variant="caption" weight="semibold" color={colors.primary} style={{ marginTop: 3 }}>
            Tap to test the connection
          </Txt>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
