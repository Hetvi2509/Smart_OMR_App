import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useAuth } from '../store/auth';
import { spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import { Button, Card, Field, Notice, Txt, useToast } from '../ui';

export default function SignUpScreen({ navigation }: any) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { signUp } = useAuth();
  const toast = useToast();

  const [form, setForm] = useState({
    full_name: '', email: '', institution_name: '', password: '', confirm: '',
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    setError(null);
    if (!form.full_name.trim()) return setError('Enter your name.');
    if (!form.email.trim()) return setError('Enter your email address.');
    // Checked here as well as on the server so the user is not told to retype
    // a password after a round trip.
    if (form.password.length < 8) {
      return setError('Choose a password of at least 8 characters.');
    }
    if (form.password !== form.confirm) {
      return setError('The two passwords do not match.');
    }

    setBusy(true);
    try {
      await signUp({
        email: form.email,
        password: form.password,
        full_name: form.full_name.trim(),
        institution_name: form.institution_name.trim() || null,
      });
      toast.show('Account created. Welcome.', 'success');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
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
          paddingTop: insets.top + spacing.lg,
          paddingBottom: insets.bottom + spacing.xl,
        }}
        keyboardShouldPersistTaps="handled"
      >
        <Txt variant="display" weight="bold" style={{ marginBottom: 4 }}>
          Create account
        </Txt>
        <Txt variant="small" muted style={{ marginBottom: spacing.xl }}>
          Set up your institute's evaluation workspace.
        </Txt>

        <Card>
          {!!error && <Notice tone="danger" title="Could not create the account" body={error} />}

          <Field label="Full name" required value={form.full_name}
                 onChangeText={set('full_name')} placeholder="Anita Desai"
                 editable={!busy} autoComplete="name" />
          <Field label="Email" required value={form.email}
                 onChangeText={set('email')} placeholder="teacher@institute.edu"
                 autoCapitalize="none" keyboardType="email-address"
                 autoComplete="email" editable={!busy} />
          <Field label="Institute" value={form.institution_name}
                 onChangeText={set('institution_name')}
                 placeholder="Infra Coaching Institute"
                 hint="Shown on generated result reports."
                 editable={!busy} />
          <Field label="Password" required value={form.password}
                 onChangeText={set('password')} placeholder="At least 8 characters"
                 secureTextEntry editable={!busy} />
          <Field label="Confirm password" required value={form.confirm}
                 onChangeText={set('confirm')} placeholder="Repeat the password"
                 secureTextEntry editable={!busy}
                 onSubmitEditing={submit} returnKeyType="go" />

          <Button title="Create account" onPress={submit} loading={busy} fullWidth />

          <Pressable
            onPress={() => navigation.goBack()}
            style={{ marginTop: spacing.lg, alignItems: 'center' }}
            disabled={busy}
          >
            <Txt variant="small" muted>
              Already registered?{' '}
              <Txt variant="small" weight="bold" color={colors.primary}>Sign in</Txt>
            </Txt>
          </Pressable>
        </Card>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
