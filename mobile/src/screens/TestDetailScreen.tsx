import React, { useState } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useScreenInsets } from '../hooks/useScreenInsets';

import { endpoints } from '../api/endpoints';
import { num } from '../api/types';
import { invalidate, useApi } from '../hooks/useApi';
import { spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import ScanIcon from '../ui/icons/ScanIcon';
import {
  Badge, Button, Card, Dialog, ErrorState, Notice, Row, SectionHeader,
  Stat, Txt, useToast,
} from '../ui';
import { Bone, ListSkeleton, StatSkeleton } from '../ui/skeleton';

export default function TestDetailScreen({ route, navigation }: any) {
  const testId: number = route.params.testId;
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const screen = useScreenInsets();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const { data, error, loading, refreshing, refresh, reload } = useApi(
    async () => {
      const [t, results] = await Promise.all([
        endpoints.getTest(testId),
        endpoints.testResults(testId),
      ]);
      return { test: t.test, ...results };
    },
    [testId],
    { key: `test:${testId}` },
  );

  if (loading && !data) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.background,
                     padding: spacing.lg, paddingTop: screen.top }}>
        <Bone width="60%" height={28} />
        <Bone width="40%" height={13} style={{ marginTop: 8, marginBottom: spacing.lg }} />
        <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.lg }}>
          <StatSkeleton /><StatSkeleton /><StatSkeleton />
        </View>
        <Bone width="100%" height={48} style={{ borderRadius: 12, marginBottom: spacing.lg }} />
        <ListSkeleton count={3} />
      </View>
    );
  }
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return null;

  const { test, results, summary } = data;
  const keyCount = test.key_count ?? 0;
  const ready = keyCount > 0;

  const remove = async () => {
    setDeleting(true);
    try {
      await endpoints.deleteTest(testId);
      // A deleted test takes its submissions and reports with it.
      invalidate('tests');
      invalidate(`test:${testId}`);
      invalidate('results');
      invalidate('reports');
      invalidate('dashboard');
      toast.show('Test deleted.', 'success');
      navigation.navigate('Main', { screen: 'Tests' });
    } catch (err) {
      toast.show((err as Error).message, 'error');
      setDeleting(false);
      setConfirm(false);
    }
  };

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
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md }}>
          <View style={{ flex: 1 }}>
            <Txt variant="display" weight="bold">{test.name}</Txt>
            <Txt variant="small" muted style={{ marginTop: 2 }}>
              {[test.subject, test.layout.toUpperCase(),
                `${test.total_questions} questions`].filter(Boolean).join(' · ')}
            </Txt>
          </View>
          <Badge label={ready ? 'Ready' : 'Draft'} tone={ready ? 'success' : 'muted'} />
        </View>

        {!ready && (
          <Notice
            tone="warning"
            title="No answer key yet"
            body="A sheet is scored against the key stored for this test, so scanning is blocked until you add one."
          />
        )}

        <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.lg, marginBottom: spacing.lg }}>
          <Stat label="Answer key" value={ready ? keyCount : '—'}
                tone={ready ? colors.success : colors.destructive}
                hint={ready ? 'answers stored' : 'not added'} />
          <Stat label="Evaluated" value={summary.evaluated ?? 0} hint="sheets" />
          <Stat label="Average"
                value={summary.avg_pct === null ? '—' : `${num(summary.avg_pct).toFixed(1)}%`}
                tone={colors.primary} />
        </View>

        <View style={{ gap: spacing.sm, marginBottom: spacing.xl }}>
          <Button title={ready ? 'Scan a sheet for this test' : 'Add answer key first'}
                  icon={ready
                      ? <ScanIcon size={18} color={colors.primaryForeground}
                                  documentColor="#FFFFFF" lineColor={colors.primary} />
                      : undefined}
                  onPress={() => ready
                      ? navigation.navigate('Main', { screen: 'Scan', params: { testId } })
                      : navigation.navigate('AnswerKey', { testId })}
                  fullWidth />
          <View style={{ flexDirection: 'row', gap: spacing.sm }}>
            <Button title={ready ? 'Edit key' : 'Add key'} variant="outline"
                    style={{ flex: 1 }}
                    onPress={() => navigation.navigate('AnswerKey', { testId })} />
            <Button title="Edit test" variant="outline" style={{ flex: 1 }}
                    onPress={() => navigation.navigate('EditTest', { testId })} />
          </View>
        </View>

        <SectionHeader title="Marking scheme" />
        <Card padded={false} style={{ padding: spacing.md, marginBottom: spacing.xl }}>
          <Row label="Correct answer" value={`+${test.marks_correct}`} tone={colors.success} />
          <Row label="Wrong answer" value={String(test.marks_wrong)}
               tone={num(test.marks_wrong) < 0 ? colors.destructive : undefined} />
          <Row label="Unanswered" value={String(test.marks_blank)} />
          <Row label="Two bubbles marked" value={test.ambiguous_policy} />
          <Row label="Negative total" value={test.floor_at_zero ? 'Floored at zero' : 'Allowed'} last />
        </Card>

        <SectionHeader
          title="Results"
          subtitle={summary.evaluated ? 'Ranked by percentage' : undefined}
          action={
            results.length > 0 ? (
              <Button title="All" variant="ghost" size="sm"
                      onPress={() => navigation.navigate('Main', { screen: 'History', params: { testId } })} />
            ) : undefined
          }
        />
        {results.length === 0 ? (
          <Card>
            <Txt variant="small" muted center>
              No sheets scanned for this test yet.
            </Txt>
          </Card>
        ) : (
          <Card padded={false} style={{ padding: spacing.md }}>
            {results.slice(0, 15).map((r, i, arr) => (
              <Row
                key={r.submission_id}
                label={`${i + 1}. ${r.student_name || r.roll_no || `Sheet #${r.submission_id}`}`}
                value={
                  r.status === 'completed'
                    ? `${num(r.percentage).toFixed(1)}%  (${num(r.total_marks)}/${num(r.max_marks)})`
                    : r.status
                }
                tone={r.status === 'completed' ? colors.primary : colors.mutedForeground}
                last={i === Math.min(arr.length, 15) - 1}
              />
            ))}
          </Card>
        )}

        <Button title="Delete this test" variant="ghost" fullWidth
                style={{ marginTop: spacing.xl }} onPress={() => setConfirm(true)} />
      </ScrollView>

      <Dialog
        visible={confirm}
        title="Delete this test?"
        message={`The test, its answer key${
          (test.submission_count ?? 0) > 0
            ? ` and all ${test.submission_count} scanned sheets with their results`
            : ''
        } will be permanently removed. This cannot be undone.`}
        confirmLabel="Delete"
        destructive
        loading={deleting}
        onConfirm={remove}
        onCancel={() => setConfirm(false)}
      />
    </View>
  );
}
