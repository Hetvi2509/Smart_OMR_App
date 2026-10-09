import React, { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useScreenInsets } from '../hooks/useScreenInsets';

import { endpoints } from '../api/endpoints';
import { invalidate } from '../hooks/useApi';
import { LayoutInfo, Test } from '../api/types';
import { spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import {
  Button, Card, Field, Loading, Notice, Segmented, Txt, useToast,
} from '../ui';

const POLICIES = [
  { value: 'wrong', label: 'Count as wrong' },
  { value: 'blank', label: 'Count as blank' },
  { value: 'zero', label: 'Void (0 marks)' },
  { value: 'review', label: 'Hold for review' },
];

export default function EditTestScreen({ route, navigation }: any) {
  const editingId: number | undefined = route.params?.testId;
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const screen = useScreenInsets();
  const toast = useToast();

  const [layouts, setLayouts] = useState<LayoutInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    name: '', subject: '', exam_date: '', layout: 'neet',
    total_questions: '200', marks_correct: '4', marks_wrong: '-1',
    marks_blank: '0', ambiguous_policy: 'wrong', floor_at_zero: true,
  });
  const set = (k: keyof typeof form) => (v: any) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    (async () => {
      try {
        const [l, existing] = await Promise.all([
          endpoints.layouts(),
          editingId ? endpoints.getTest(editingId) : Promise.resolve(null),
        ]);
        setLayouts(l.layouts);
        if (existing) {
          const t = existing.test;
          setForm({
            name: t.name,
            subject: t.subject || '',
            exam_date: t.exam_date || '',
            layout: t.layout,
            total_questions: String(t.total_questions),
            marks_correct: String(t.marks_correct),
            marks_wrong: String(t.marks_wrong),
            marks_blank: String(t.marks_blank),
            ambiguous_policy: t.ambiguous_policy,
            floor_at_zero: t.floor_at_zero,
          });
        }
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, [editingId]);

  /** Picking a layout sets the question count it implies, which is almost
   *  always what the user wants and avoids a mismatch the scan would hit. */
  const pickLayout = (key: string) => {
    const l = layouts.find((x) => x.key === key);
    setForm((f) => ({
      ...f,
      layout: key,
      total_questions: l ? String(l.total_questions) : f.total_questions,
    }));
  };

  const submit = async () => {
    setError(null);
    if (!form.name.trim()) return setError('Give the test a name.');
    const total = parseInt(form.total_questions, 10);
    if (!Number.isFinite(total) || total < 1) {
      return setError('Enter how many questions the test has.');
    }
    if (form.exam_date && !/^\d{4}-\d{2}-\d{2}$/.test(form.exam_date.trim())) {
      return setError('Write the exam date as YYYY-MM-DD, or leave it empty.');
    }

    const chosen = layouts.find((l) => l.key === form.layout);
    const body: Partial<Test> = {
      name: form.name.trim(),
      subject: form.subject.trim() || null,
      exam_date: form.exam_date.trim() || null,
      layout: form.layout,
      total_questions: total,
      options: (chosen?.options ?? ['A', 'B', 'C', 'D']).join(','),
      marks_correct: parseFloat(form.marks_correct) || 0,
      marks_wrong: parseFloat(form.marks_wrong) || 0,
      marks_blank: parseFloat(form.marks_blank) || 0,
      ambiguous_policy: form.ambiguous_policy,
      floor_at_zero: form.floor_at_zero,
    };

    setBusy(true);
    try {
      if (editingId) {
        await endpoints.updateTest(editingId, body);
        invalidate('tests');
        invalidate(`test:${editingId}`);
        invalidate('dashboard');
        toast.show('Test updated.', 'success');
        navigation.goBack();
      } else {
        const res = await endpoints.createTest(body);
        invalidate('tests');
        invalidate('dashboard');
        toast.show('Test created. Now add its answer key.', 'success');
        // Straight to the answer key: a test without one cannot be scanned,
        // so sending the user back to the list would just add a step.
        navigation.replace('AnswerKey', { testId: res.test.id });
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Loading text="Loading sheet layouts…" />;

  const chosen = layouts.find((l) => l.key === form.layout);

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.background }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        contentContainerStyle={{
          padding: spacing.lg,
          paddingTop: screen.top,
          paddingBottom: screen.stackBottom,
        }}
        keyboardShouldPersistTaps="handled"
      >
        <Txt variant="display" weight="bold">
          {editingId ? 'Edit test' : 'New test'}
        </Txt>
        <Txt variant="small" muted style={{ marginTop: 2, marginBottom: spacing.lg }}>
          These settings decide how every sheet for this test is read and scored.
        </Txt>

        {!!error && <Notice tone="danger" title="Check the form" body={error} />}

        <Card style={{ marginBottom: spacing.lg }}>
          <Txt variant="heading" weight="bold" style={{ marginBottom: spacing.lg }}>
            Details
          </Txt>
          <Field label="Test name" required value={form.name}
                 onChangeText={set('name')} placeholder="NEET Mock Test 4"
                 editable={!busy} />
          <Field label="Subject" value={form.subject} onChangeText={set('subject')}
                 placeholder="Physics, Chemistry, Biology" editable={!busy} />
          <Field label="Exam date" value={form.exam_date}
                 onChangeText={set('exam_date')} placeholder="2026-03-15"
                 hint="Format YYYY-MM-DD. Optional." editable={!busy} />
        </Card>

        <Card style={{ marginBottom: spacing.lg }}>
          <Txt variant="heading" weight="bold" style={{ marginBottom: spacing.lg }}>
            Sheet layout
          </Txt>
          <Segmented
            label="Which printed form is used?"
            options={layouts.map((l) => ({ value: l.key, label: l.name }))}
            value={form.layout}
            onChange={pickLayout}
          />
          {!!chosen && (
            <Notice
              tone="info"
              title={`${chosen.name}: ${chosen.total_questions} questions`}
              body={`${chosen.blocks} block(s) of ${chosen.rows_per_block} rows, options ${chosen.options.join('/')}${
                chosen.subjects.length ? ` · ${chosen.subjects.join(', ')}` : ''}`}
            />
          )}
          <Field label="Total questions" required value={form.total_questions}
                 onChangeText={set('total_questions')} keyboardType="number-pad"
                 hint="Set from the layout; change it only for a partial paper."
                 editable={!busy} />
        </Card>

        <Card style={{ marginBottom: spacing.lg }}>
          <Txt variant="heading" weight="bold" style={{ marginBottom: 4 }}>
            Marking scheme
          </Txt>
          <Txt variant="small" muted style={{ marginBottom: spacing.lg }}>
            Applied automatically when a sheet is scored.
          </Txt>
          <View style={{ flexDirection: 'row', gap: spacing.sm }}>
            <View style={{ flex: 1 }}>
              <Field label="Correct" value={form.marks_correct}
                     onChangeText={set('marks_correct')} keyboardType="numbers-and-punctuation"
                     editable={!busy} />
            </View>
            <View style={{ flex: 1 }}>
              <Field label="Wrong" value={form.marks_wrong}
                     onChangeText={set('marks_wrong')} keyboardType="numbers-and-punctuation"
                     editable={!busy} />
            </View>
            <View style={{ flex: 1 }}>
              <Field label="Blank" value={form.marks_blank}
                     onChangeText={set('marks_blank')} keyboardType="numbers-and-punctuation"
                     editable={!busy} />
            </View>
          </View>
          <Segmented
            label="If two bubbles are marked"
            options={POLICIES}
            value={form.ambiguous_policy}
            onChange={set('ambiguous_policy')}
          />
          <Segmented
            label="Negative total"
            options={[
              { value: 'yes', label: 'Floor at zero' },
              { value: 'no', label: 'Allow negative' },
            ]}
            value={form.floor_at_zero ? 'yes' : 'no'}
            onChange={(v) => set('floor_at_zero')(v === 'yes')}
          />
        </Card>

        <Button
          title={editingId ? 'Save changes' : 'Create test and add answer key'}
          onPress={submit}
          loading={busy}
          fullWidth
        />
        <Button title="Cancel" variant="ghost" onPress={() => navigation.goBack()}
                disabled={busy} style={{ marginTop: spacing.sm }} fullWidth />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
