import React, { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useScreenInsets } from '../hooks/useScreenInsets';

import { endpoints } from '../api/endpoints';
import { invalidate } from '../hooks/useApi';
import { parseKeyText } from '../lib/parseKeyText';
import { Test } from '../api/types';
import { radius, spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import {
  Button, Card, Dialog, ErrorState, Field, Loading, Notice, Segmented, Txt,
  useToast,
} from '../ui';

export default function AnswerKeyScreen({ route, navigation }: any) {
  const testId: number = route.params.testId;
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const screen = useScreenInsets();
  const toast = useToast();

  const [test, setTest] = useState<Test | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState('');
  const [page, setPage] = useState(0);

  const PER_PAGE = 50;

  useEffect(() => {
    (async () => {
      try {
        const [t, key] = await Promise.all([
          endpoints.getTest(testId),
          endpoints.getAnswerKey(testId),
        ]);
        setTest(t.test);
        const map: Record<number, string> = {};
        key.entries.forEach((e) => { map[e.question_no] = e.correct_option; });
        setAnswers(map);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, [testId]);

  const options = useMemo(
    () => (test?.options || 'A,B,C,D').split(',').map((o) => o.trim()).filter(Boolean),
    [test],
  );
  const total = test?.total_questions ?? 0;
  const filled = Object.keys(answers).length;

  const save = async () => {
    if (filled === 0) {
      setError('Set at least one answer before saving.');
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const entries = Object.entries(answers)
        .map(([q, o]) => ({ question_no: Number(q), correct_option: o }))
        .sort((a, b) => a.question_no - b.question_no);
      await endpoints.putAnswerKey(testId, entries);
      // The key decides whether a test can be scanned, so the lists that
      // show that state must not keep serving the old answer.
      invalidate('tests');
      invalidate(`test:${testId}`);
      invalidate('dashboard');
      toast.show(`Answer key saved — ${entries.length} answers.`, 'success');
      navigation.goBack();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const runImport = () => {
    const { answers: parsed, errors } = parseKeyText(importText, options);
    const count = Object.keys(parsed).length;
    if (count === 0) {
      toast.show(errors[0] || 'Nothing could be read from that text.', 'error');
      return;
    }
    const beyond = Object.keys(parsed).filter((q) => Number(q) > total);
    if (beyond.length) {
      toast.show(
        `${beyond.length} answer(s) are past this test's ${total} questions and were skipped.`,
        'error',
      );
      beyond.forEach((q) => delete parsed[Number(q)]);
    }
    setAnswers((prev) => ({ ...prev, ...parsed }));
    setImportOpen(false);
    setImportText('');
    const msg = errors.length
      ? `Imported ${Object.keys(parsed).length}, skipped ${errors.length}.`
      : `Imported ${Object.keys(parsed).length} answers.`;
    toast.show(msg, errors.length ? 'error' : 'success');
  };

  if (loading) return <Loading text="Loading answer key…" />;
  if (!test) return <ErrorState message={error || 'Test not found.'} />;

  const pages = Math.max(1, Math.ceil(total / PER_PAGE));
  const start = page * PER_PAGE + 1;
  const end = Math.min(total, (page + 1) * PER_PAGE);
  const visible = Array.from({ length: Math.max(0, end - start + 1) }, (_, i) => start + i);

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <ScrollView
        contentContainerStyle={{
          padding: spacing.lg,
          paddingTop: screen.top,
          // Clears the pinned Save footer as well as the device inset;
          // without the extra height the last question hides behind it.
          paddingBottom: screen.stackBottom + 72,
        }}
      >
        <Txt variant="display" weight="bold">Answer key</Txt>
        <Txt variant="small" muted style={{ marginTop: 2 }} numberOfLines={2}>
          {test.name}
        </Txt>

        <Card style={{ marginTop: spacing.lg, marginBottom: spacing.lg }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <View>
              <Txt variant="caption" muted weight="semibold">PROGRESS</Txt>
              <Txt variant="title" weight="bold" color={filled === total ? colors.success : colors.primary}>
                {filled} / {total}
              </Txt>
            </View>
            <Button title="Paste / import" variant="outline" size="sm"
                    onPress={() => setImportOpen(true)} />
          </View>
          {filled > 0 && filled < total && (
            <Txt variant="caption" muted style={{ marginTop: spacing.sm }}>
              Questions with no answer here are left unscored — they never count
              against a student.
            </Txt>
          )}
        </Card>

        {!!error && <Notice tone="danger" title="Could not save" body={error} />}

        {pages > 1 && (
          <Segmented
            label="Questions"
            options={Array.from({ length: pages }, (_, i) => ({
              value: i,
              label: `${i * PER_PAGE + 1}–${Math.min(total, (i + 1) * PER_PAGE)}`,
            }))}
            value={page}
            onChange={setPage}
          />
        )}

        <Card padded={false} style={{ padding: spacing.md }}>
          {visible.map((q) => (
            <View
              key={q}
              style={{
                flexDirection: 'row', alignItems: 'center',
                paddingVertical: 7, gap: spacing.sm,
              }}
            >
              <Txt variant="small" weight="bold" mono
                   style={{ width: 38 }} color={answers[q] ? colors.foreground : colors.mutedForeground}>
                {q}
              </Txt>
              <View style={{ flexDirection: 'row', gap: 6, flex: 1 }}>
                {options.map((opt) => {
                  const on = answers[q] === opt.toUpperCase();
                  return (
                    <Pressable
                      key={opt}
                      accessibilityRole="radio"
                      accessibilityState={{ selected: on }}
                      accessibilityLabel={`Question ${q}, option ${opt}`}
                      onPress={() =>
                        setAnswers((prev) => {
                          const next = { ...prev };
                          // Tapping the set option again clears it, which is
                          // the only way to undo a mistake on a touch grid.
                          if (on) delete next[q];
                          else next[q] = opt.toUpperCase();
                          return next;
                        })
                      }
                      style={{
                        flex: 1, height: 38, borderRadius: radius.sm,
                        borderWidth: 1.5,
                        borderColor: on ? colors.primary : colors.border,
                        backgroundColor: on ? colors.primary : colors.card,
                        alignItems: 'center', justifyContent: 'center',
                      }}
                    >
                      <Txt variant="small" weight="bold"
                           color={on ? colors.primaryForeground : colors.foreground}>
                        {opt}
                      </Txt>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          ))}
        </Card>
      </ScrollView>

      {/* Save is pinned: with 200 questions the bottom of the list is a long
          way from the top, and the user must be able to save at any point. */}
      <View
        style={{
          position: 'absolute', left: 0, right: 0, bottom: 0,
          padding: spacing.lg, paddingBottom: insets.bottom + spacing.md,
          backgroundColor: colors.card, borderTopWidth: 1.5,
          borderTopColor: colors.border, flexDirection: 'row', gap: spacing.sm,
        }}
      >
        <Button title="Clear all" variant="outline"
                onPress={() => setAnswers({})} disabled={saving || filled === 0} />
        <Button title={`Save key (${filled})`} onPress={save} loading={saving}
                style={{ flex: 1 }} />
      </View>

      <Dialog
        visible={importOpen}
        title="Import answers"
        message="Paste the key. Accepts ABCDA…, comma-separated letters, or numbered lines like “1. C”. Digits 1-4 are read as the option in that position."
        confirmLabel="Import"
        onConfirm={runImport}
        onCancel={() => setImportOpen(false)}
      >
        <View style={{ marginTop: spacing.lg }}>
          <Field
            value={importText}
            onChangeText={setImportText}
            placeholder={'1. C\n2. A\n3. D\n\nor: CADB CADB …'}
            multiline
            numberOfLines={6}
            style={{ minHeight: 130, textAlignVertical: 'top' }}
            autoCapitalize="characters"
          />
        </View>
      </Dialog>
    </View>
  );
}
