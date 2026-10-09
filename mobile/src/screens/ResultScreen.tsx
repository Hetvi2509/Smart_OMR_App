import React, { useCallback, useMemo, useState } from 'react';
import { Image, Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useScreenInsets } from '../hooks/useScreenInsets';

import { endpoints } from '../api/endpoints';
import { EvaluationItem, num } from '../api/types';
import { invalidate, useApi } from '../hooks/useApi';
import { SheetVariant, useSheetImage } from '../hooks/useSheetImage';
import { openReportPdf } from '../lib/reportFile';
import { radius, spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import ScanIcon from '../ui/icons/ScanIcon';
import {
  Badge, Button, Card, Dialog, ErrorState, Field, MiniBar, Notice,
  Row, SectionHeader, Segmented, Txt, useToast,
} from '../ui';
import { ResultSkeleton } from '../ui/skeleton';

type Filter = 'all' | 'correct' | 'wrong' | 'unattempted' | 'review';

export default function ResultScreen({ route, navigation }: any) {
  const submissionId: number = route.params.submissionId;
  const justScanned: boolean = route.params?.justScanned ?? false;
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const screen = useScreenInsets();
  const toast = useToast();

  const { data, error, loading, refreshing, refresh, reload, setData } =
    useApi(() => endpoints.getResult(submissionId), [submissionId],
            { key: `result:${submissionId}` });

  const [editOpen, setEditOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [filter, setFilter] = useState<Filter>('all');
  const [form, setForm] = useState({
    roll_no: '', student_name: '', class_std: '', section: '', registration_no: '',
  });

  const [fixOpen, setFixOpen] = useState<EvaluationItem | null>(null);
  const [fixing, setFixing] = useState(false);

  // Every hook must run before any early return below, otherwise the render
  // that shows the loading state calls fewer hooks than the one that shows
  // the result, and React throws "Rendered more hooks than during the
  // previous render". It reads from `data` rather than the destructured
  // `items`, which is not available until after those returns.
  const filtered = useMemo(() => {
    const items = data?.items ?? [];
    switch (filter) {
      case 'correct': return items.filter((i) => i.status === 'correct');
      case 'wrong': return items.filter((i) => i.status === 'wrong' || i.status === 'invalid');
      case 'unattempted': return items.filter((i) => i.status === 'unattempted');
      case 'review': return items.filter((i) => i.needs_review);
      default: return items.filter((i) => i.status !== 'unscored');
    }
  }, [data, filter]);

  // Stable across renders so the memoised QuestionRow actually skips work:
  // an inline arrow would be a new prop every time and defeat React.memo.
  const openFix = useCallback((item: EvaluationItem) => setFixOpen(item), []);

  // A 200-question sheet rendered every row on mount, which is the single
  // biggest cost in opening a result. Rows are revealed a page at a time
  // instead; a FlatList is not an option here because the list lives inside
  // the screen's ScrollView, and nesting the two breaks virtualisation.
  const PAGE = 25;
  const [shown, setShown] = useState(PAGE);

  // Also above the early returns, for the same reason.
  // Defaults to the detected overlay: the whole point of opening a result is
  // to check what the algorithm read, and the plain photo is one tap away.
  const [sheetView, setSheetView] = useState<SheetVariant>('annotated');
  const sheet = useSheetImage(submissionId, sheetView);

  if (loading && !data) {
    return (
      <ScrollView
        style={{ flex: 1, backgroundColor: colors.background }}
        contentContainerStyle={{ padding: spacing.lg, paddingTop: insets.top + spacing.md }}
      >
        <ResultSkeleton />
      </ScrollView>
    );
  }
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return null;

  const { submission, test, candidate, evaluation, items } = data;
  const options = (test.options || 'A,B,C,D').split(',').map((o) => o.trim()).filter(Boolean);

  if (submission.status === 'failed') {
    return (
      <ScrollView
        style={{ flex: 1, backgroundColor: colors.background }}
        contentContainerStyle={{ padding: spacing.lg, paddingTop: insets.top + spacing.md }}
      >
        <Txt variant="display" weight="bold">Sheet not read</Txt>
        <Txt variant="small" muted style={{ marginTop: 2, marginBottom: spacing.lg }}>
          {test.name}
        </Txt>
        <Notice
          tone="danger"
          title={submission.error_reason || 'Unreadable'}
          body={submission.error_hint ||
            'The reader could not locate the answer grid on this image.'}
        />
        <Card style={{ marginBottom: spacing.lg }}>
          <Txt variant="small" weight="bold" style={{ marginBottom: spacing.sm }}>
            What usually fixes it
          </Txt>
          <Txt variant="small" muted>
            • Get the whole ruled answer table in frame{'\n'}
            • Hold the camera square to the page, not at an angle{'\n'}
            • Avoid a shadow or glare across the bubbles{'\n'}
            • Make sure the chosen test matches the printed form
          </Txt>
        </Card>
        <Button title="Scan again"
                icon={<ScanIcon size={18} color={colors.primaryForeground}
                                documentColor="#FFFFFF" lineColor={colors.primary} />}
                onPress={() => navigation.navigate('Main', { screen: 'Scan', params: { testId: test.id } })} fullWidth />
        <Button title="Back to history" variant="ghost" fullWidth
                style={{ marginTop: spacing.sm }}
                onPress={() => navigation.navigate('Main', { screen: 'History' })} />
      </ScrollView>
    );
  }

  const openEdit = () => {
    setForm({
      roll_no: candidate.roll_no || '',
      student_name: candidate.student_name || '',
      class_std: candidate.class_std || '',
      section: candidate.section || '',
      registration_no: candidate.registration_no || '',
    });
    setEditOpen(true);
  };

  const saveCandidate = async () => {
    setSaving(true);
    try {
      const res = await endpoints.editCandidate(submissionId, {
        roll_no: form.roll_no.trim() || null,
        student_name: form.student_name.trim() || null,
        class_std: form.class_std.trim() || null,
        section: form.section.trim() || null,
        registration_no: form.registration_no.trim() || null,
      });
      setData({ ...data, candidate: { ...data.candidate, ...res.candidate } });
      setEditOpen(false);
      toast.show('Candidate details saved.', 'success');
    } catch (err) {
      toast.show((err as Error).message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const applyFix = async (option: string | null) => {
    if (!fixOpen) return;
    setFixing(true);
    try {
      await endpoints.overrideAnswers(submissionId, [
        { question_no: fixOpen.question_no, marked_option: option },
      ]);
      setFixOpen(null);
      // Re-scoring moves the total, so history and the dashboard averages
      // computed from it are now stale.
      invalidate('results');
      invalidate('dashboard');
      toast.show(`Question ${fixOpen.question_no} updated and re-scored.`, 'success');
      await refresh();
    } catch (err) {
      toast.show((err as Error).message, 'error');
    } finally {
      setFixing(false);
    }
  };

  const generateReport = async () => {
    setReporting(true);
    try {
      const { report } = await endpoints.createReport(submissionId);
      invalidate('reports');
      invalidate('dashboard');
      const shared = await openReportPdf(report.id);
      toast.show(shared ? 'Report generated.' : 'Report saved to this device.',
                 'success');
      await refresh();
    } catch (err) {
      toast.show((err as Error).message, 'error');
    } finally {
      setReporting(false);
    }
  };

  const removeResult = async () => {
    setDeleting(true);
    try {
      await endpoints.deleteResult(submissionId);
      invalidate(`result:${submissionId}`);
      invalidate('results');
      invalidate('dashboard');
      invalidate('reports');
      toast.show('Result deleted.', 'success');
      navigation.navigate('Main', { screen: 'History' });
    } catch (err) {
      toast.show((err as Error).message, 'error');
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  const pct = num(evaluation?.percentage);
  const needsIdentity = !candidate.student_name && !candidate.roll_no;

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <ScrollView
        contentContainerStyle={{
          padding: spacing.lg,
          paddingTop: screen.top,
          paddingBottom: screen.stackBottom,
        }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={refresh}
                          tintColor={colors.primary} />
        }
      >
        {justScanned && (
          <Notice tone="success" title="Sheet evaluated"
                  body="Check the candidate details below, correct anything the reader got wrong, then generate the report." />
        )}

        <Txt variant="small" muted numberOfLines={1}>{test.name}</Txt>
        <Txt variant="display" weight="bold" style={{ marginTop: 2 }}>
          {candidate.student_name || candidate.roll_no || `Sheet #${submissionId}`}
        </Txt>

        {/* score */}
        <Card style={{ marginTop: spacing.lg, marginBottom: spacing.lg }}>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between' }}>
            <View>
              <Txt variant="caption" muted weight="bold">MARKS OBTAINED</Txt>
              <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 6 }}>
                <Txt variant="display" weight="bold" color={colors.primary}>
                  {num(evaluation?.total_marks)}
                </Txt>
                <Txt variant="heading" muted style={{ marginBottom: 3 }}>
                  / {num(evaluation?.max_marks)}
                </Txt>
              </View>
            </View>
            <View style={{ alignItems: 'flex-end' }}>
              <Badge label={`Grade ${evaluation?.grade ?? '—'}`}
                     tone={pct >= 60 ? 'success' : pct >= 40 ? 'warning' : 'danger'} />
              <Txt variant="title" weight="bold" style={{ marginTop: 6 }}>
                {pct.toFixed(1)}%
              </Txt>
            </View>
          </View>

          <View style={{ marginTop: spacing.lg }}>
            <MiniBar segments={[
              { value: evaluation?.correct_count ?? 0, color: colors.success },
              { value: evaluation?.wrong_count ?? 0, color: colors.destructive },
              { value: evaluation?.invalid_count ?? 0, color: colors.accent },
              { value: evaluation?.unattempted_count ?? 0, color: colors.muted },
            ]} />
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md, marginTop: spacing.sm }}>
              <Legend color={colors.success} label="Correct" value={evaluation?.correct_count ?? 0} />
              <Legend color={colors.destructive} label="Wrong" value={evaluation?.wrong_count ?? 0} />
              <Legend color={colors.accent} label="Invalid" value={evaluation?.invalid_count ?? 0} />
              <Legend color={colors.mutedForeground} label="Blank" value={evaluation?.unattempted_count ?? 0} />
            </View>
          </View>
        </Card>

        {/* the sheet, as scanned and as read */}
        <SectionHeader
          title="Scanned sheet"
          subtitle={sheetView === 'annotated'
            ? 'Every bubble the reader detected is ringed'
            : 'The photo exactly as it was uploaded'}
        />
        <Segmented
          options={[
            { value: 'annotated', label: 'Detected answers' },
            { value: 'original', label: 'Original photo' },
          ]}
          value={sheetView}
          onChange={(v) => setSheetView(v as SheetVariant)}
        />
        <Card padded={false} style={{ padding: spacing.sm, marginBottom: spacing.lg }}>
          {sheet.source ? (
            <Image
              source={sheet.source}
              style={{
                width: '100%',
                aspectRatio: 0.7,
                borderRadius: radius.md,
                backgroundColor: colors.muted,
              }}
              resizeMode="contain"
              accessibilityLabel={sheetView === 'annotated'
                ? 'The answer sheet with detected bubbles ringed'
                : 'The answer sheet as photographed'}
            />
          ) : (
            <View style={{
              width: '100%', aspectRatio: 0.7, borderRadius: radius.md,
              backgroundColor: colors.muted, alignItems: 'center',
              justifyContent: 'center',
            }}>
              <Txt variant="small" muted center>
                {sheet.failed
                  ? (sheetView === 'annotated'
                      ? 'No review overlay was stored for this sheet.'
                      : 'The scanned image is no longer on the server.')
                  : 'Loading image…'}
              </Txt>
            </View>
          )}
          {sheetView === 'annotated' && !!sheet.source && (
            <View style={{ flexDirection: 'row', gap: spacing.md, padding: spacing.sm, flexWrap: 'wrap' }}>
              <Legend color={colors.success} label="Matches the key" value={evaluation?.correct_count ?? 0} />
              <Legend color={colors.destructive} label="Does not match" value={evaluation?.wrong_count ?? 0} />
            </View>
          )}
        </Card>

        {/* candidate */}
        <SectionHeader
          title="Candidate details"
          subtitle={candidate.engine
            ? `Read by ${candidate.engine}${candidate.confidence ? ` · ${(num(candidate.confidence) * 100).toFixed(0)}% confidence` : ''}`
            : 'Entered manually'}
          action={<Button title="Edit" variant="ghost" size="sm" onPress={openEdit} />}
        />
        {needsIdentity && (
          <Notice
            tone="warning"
            title="No candidate details were read"
            body="The sheet header could not be matched. Tap Edit to enter the roll number and name — they appear on the report."
          />
        )}
        <Card padded={false} style={{ padding: spacing.md, marginBottom: spacing.lg }}>
          <Row label="Student name" value={candidate.student_name || '—'} />
          <Row label="Roll number" value={candidate.roll_no || '—'} mono />
          <Row label="Registration no." value={candidate.registration_no || '—'} mono />
          <Row label="Class / standard" value={candidate.class_std || '—'} />
          <Row label="Section" value={candidate.section || '—'} last />
        </Card>

        {/* meta */}
        <SectionHeader title="Evaluation details" />
        <Card padded={false} style={{ padding: spacing.md, marginBottom: spacing.lg }}>
          <Row label="Answers detected" value={`${submission.answered_count ?? 0} of ${test.total_questions}`} />
          <Row label="Sheet layout" value={submission.layout_used || test.layout} />
          <Row label="Flagged for review" value={submission.review_questions?.length ?? 0}
               tone={(submission.review_questions?.length ?? 0) > 0 ? colors.accent : undefined} />
          <Row label="Not in answer key" value={evaluation?.unscored_count ?? 0} />
          <Row label="Processing time" value={`${submission.processing_ms ?? 0} ms`} />
          <Row label="Evaluated at"
               value={evaluation ? new Date(evaluation.evaluated_at).toLocaleString() : '—'} last />
        </Card>

        {Object.keys(evaluation?.subject_scores ?? {}).length > 1 && (
          <>
            <SectionHeader title="Subject-wise marks" />
            <Card padded={false} style={{ padding: spacing.md, marginBottom: spacing.lg }}>
              {Object.entries(evaluation!.subject_scores).map(([s, v], i, arr) => (
                <Row key={s} label={s} value={num(v)} last={i === arr.length - 1} />
              ))}
            </Card>
          </>
        )}

        {/* questions */}
        <SectionHeader title="Question-wise detail"
                       subtitle="Tap a question to correct what was detected" />
        <Segmented
          options={[
            { value: 'all', label: `All (${items.filter((i) => i.status !== 'unscored').length})` },
            { value: 'correct', label: `Correct (${evaluation?.correct_count ?? 0})` },
            { value: 'wrong', label: `Wrong (${(evaluation?.wrong_count ?? 0) + (evaluation?.invalid_count ?? 0)})` },
            { value: 'unattempted', label: `Blank (${evaluation?.unattempted_count ?? 0})` },
            { value: 'review', label: `Review (${items.filter((i) => i.needs_review).length})` },
          ]}
          value={filter}
          onChange={(v) => { setFilter(v as Filter); setShown(PAGE); }}
        />
        <Card padded={false} style={{ padding: spacing.sm, marginBottom: spacing.lg }}>
          {filtered.length === 0 ? (
            <Txt variant="small" muted center style={{ padding: spacing.lg }}>
              No questions in this group.
            </Txt>
          ) : (
            filtered.slice(0, shown).map((item) => (
              <QuestionRow key={item.question_no} item={item}
                           onPress={openFix} />
            ))
          )}
          {filtered.length > shown && (
            <Button
              title={`Show ${Math.min(PAGE, filtered.length - shown)} more`}
              variant="ghost"
              size="sm"
              onPress={() => setShown((n) => n + PAGE)}
              style={{ marginTop: spacing.sm }}
            />
          )}
        </Card>

        <Button title={reporting ? 'Generating…' : 'Generate report (PDF)'}
                onPress={generateReport} loading={reporting} fullWidth />
        <Button title="Scan another sheet" variant="outline"
                icon={<ScanIcon size={18} color={colors.foreground}
                                documentColor={colors.muted} lineColor={colors.primary} />}
                fullWidth
                style={{ marginTop: spacing.sm }}
                onPress={() => navigation.navigate('Main', { screen: 'Scan', params: { testId: test.id } })} />
        <Button title="Delete this result" variant="ghost" fullWidth
                style={{ marginTop: spacing.sm }}
                onPress={() => setConfirmDelete(true)} />
      </ScrollView>

      {/* edit candidate */}
      <Dialog
        visible={editOpen}
        title="Candidate details"
        message="Correct anything the reader got wrong. The original machine reading is kept for the audit trail."
        confirmLabel="Save"
        loading={saving}
        onConfirm={saveCandidate}
        onCancel={() => setEditOpen(false)}
      >
        <ScrollView style={{ maxHeight: 340, marginTop: spacing.lg }}>
          <Field label="Student name" value={form.student_name}
                 onChangeText={(v) => setForm((f) => ({ ...f, student_name: v }))}
                 placeholder="Full name" editable={!saving} />
          <Field label="Roll number" value={form.roll_no}
                 onChangeText={(v) => setForm((f) => ({ ...f, roll_no: v }))}
                 placeholder="e.g. 240571" editable={!saving} />
          <Field label="Registration no." value={form.registration_no}
                 onChangeText={(v) => setForm((f) => ({ ...f, registration_no: v }))}
                 placeholder="Optional" editable={!saving} />
          <Field label="Class / standard" value={form.class_std}
                 onChangeText={(v) => setForm((f) => ({ ...f, class_std: v }))}
                 placeholder="e.g. 12" editable={!saving} />
          <Field label="Section" value={form.section}
                 onChangeText={(v) => setForm((f) => ({ ...f, section: v }))}
                 placeholder="e.g. B" editable={!saving} />
        </ScrollView>
      </Dialog>

      {/* fix one answer */}
      <Modalish
        item={fixOpen}
        options={options}
        busy={fixing}
        onClose={() => setFixOpen(null)}
        onPick={applyFix}
      />

      <Dialog
        visible={confirmDelete}
        title="Delete this result?"
        message="The sheet, its detected answers and its evaluation are removed from the database. This cannot be undone."
        confirmLabel="Delete"
        destructive
        loading={deleting}
        onConfirm={removeResult}
        onCancel={() => setConfirmDelete(false)}
      />
    </View>
  );
}

function LegendBase({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
      <View style={{ width: 9, height: 9, borderRadius: 2, backgroundColor: color }} />
      <Txt variant="caption" muted>{label} {value}</Txt>
    </View>
  );
}

const STATUS_LABEL: Record<string, string> = {
  correct: 'Correct', wrong: 'Wrong', unattempted: 'Blank',
  invalid: 'Invalid', unscored: 'Not in key',
};

function QuestionRowBase({ item, onPress }: {
  item: EvaluationItem;
  onPress: (item: EvaluationItem) => void;
}) {
  const { colors } = useTheme();
  const tone = {
    correct: colors.success, wrong: colors.destructive,
    invalid: colors.accent, unattempted: colors.mutedForeground,
    unscored: colors.mutedForeground,
  }[item.status];

  return (
    <Pressable
      onPress={() => onPress(item)}
      style={({ pressed }) => ({
        flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
        paddingVertical: 9, paddingHorizontal: spacing.sm,
        borderRadius: radius.sm,
        backgroundColor: pressed ? colors.muted : 'transparent',
      })}
    >
      <Txt variant="small" weight="bold" mono style={{ width: 34 }}>{item.question_no}</Txt>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Txt variant="small" weight="semibold" color={tone}>
          {STATUS_LABEL[item.status] ?? item.status}
          {item.needs_review ? '  ⚠' : ''}
        </Txt>
        {!!item.subject && (
          <Txt variant="caption" muted numberOfLines={1}>{item.subject}</Txt>
        )}
      </View>
      <View style={{ alignItems: 'flex-end', minWidth: 74 }}>
        <Txt variant="small" mono>
          {item.marked_option || '–'}
          {item.expected_option && item.marked_option !== item.expected_option
            ? ` → ${item.expected_option}`
            : ''}
        </Txt>
        <Txt variant="caption" muted>{num(item.marks) > 0 ? '+' : ''}{num(item.marks)}</Txt>
      </View>
    </Pressable>
  );
}

/** The "correct one answer" sheet. Separate so the option list can be built
 *  from the test's own labels rather than hardcoded A-D. */
function Modalish({
  item, options, busy, onClose, onPick,
}: {
  item: EvaluationItem | null;
  options: string[];
  busy: boolean;
  onClose: () => void;
  onPick: (option: string | null) => void;
}) {
  const { colors } = useTheme();
  if (!item) return null;
  return (
    <Dialog
      visible
      title={`Question ${item.question_no}`}
      message={`Detected "${item.marked_option || 'blank'}", correct answer is "${item.expected_option || '—'}". Pick what the student actually marked.`}
      confirmLabel="Close"
      cancelLabel="Cancel"
      loading={busy}
      onConfirm={onClose}
      onCancel={onClose}
    >
      <View style={{ marginTop: spacing.lg, gap: spacing.sm }}>
        <View style={{ flexDirection: 'row', gap: spacing.sm }}>
          {options.map((o) => {
            const on = item.marked_option === o.toUpperCase();
            return (
              <Pressable
                key={o}
                disabled={busy}
                onPress={() => onPick(o.toUpperCase())}
                style={{
                  flex: 1, height: 46, borderRadius: radius.md, borderWidth: 1.5,
                  borderColor: on ? colors.primary : colors.border,
                  backgroundColor: on ? colors.primary : colors.card,
                  alignItems: 'center', justifyContent: 'center',
                }}
              >
                <Txt weight="bold" color={on ? colors.primaryForeground : colors.foreground}>
                  {o}
                </Txt>
              </Pressable>
            );
          })}
        </View>
        <Button title="Mark as unanswered" variant="outline" size="sm"
                disabled={busy} onPress={() => onPick(null)} fullWidth />
      </View>
    </Dialog>
  );
}

// Memoised: a long list re-renders every row whenever the screen's own
// state changes, and these rows are pure functions of their props.
const QuestionRow = React.memo(QuestionRowBase);

// Memoised: a long list re-renders every row whenever the screen's own
// state changes, and these rows are pure functions of their props.
const Legend = React.memo(LegendBase);
