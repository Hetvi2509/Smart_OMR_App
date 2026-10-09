import React from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useScreenInsets } from '../hooks/useScreenInsets';

import { endpoints } from '../api/endpoints';
import { num } from '../api/types';
import { useApi } from '../hooks/useApi';
import { useAuth } from '../store/auth';
import { spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import ScanIcon from '../ui/icons/ScanIcon';
import {
  Badge, Button, Card, ErrorState, MiniBar, Row, SectionHeader, Stat,
  Txt, statusTone,
} from '../ui';
import { DashboardSkeleton } from '../ui/skeleton';

export default function DashboardScreen({ navigation }: any) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const screen = useScreenInsets();
  const { user } = useAuth();
  const { data, error, loading, refreshing, refresh, reload } =
    useApi(() => endpoints.dashboard(), [], { key: 'dashboard' });

  if (loading && !data) {
    return (
      <ScrollView
        style={{ flex: 1, backgroundColor: colors.background }}
        contentContainerStyle={{ padding: spacing.lg, paddingTop: screen.top,
                                 paddingBottom: screen.scrollBottom }}
      >
        <DashboardSkeleton />
      </ScrollView>
    );
  }
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return null;

  const { stats, recent, by_test: byTest } = data;
  const avg = stats.avg_percentage === null ? null : num(stats.avg_percentage);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.background }}
      contentContainerStyle={{
        padding: spacing.lg,
        paddingTop: screen.top,
        paddingBottom: screen.scrollBottom,
      }}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={refresh}
                        tintColor={colors.primary} />
      }
    >
      <Txt variant="small" muted>
        {user?.institution_name || 'Smart OMR Evaluator'}
      </Txt>
      <Txt variant="display" weight="bold" style={{ marginTop: 2 }}>
        {(user?.full_name || '').split(' ')[0] || 'Welcome'}
      </Txt>
      <Txt variant="small" muted style={{ marginTop: 4, marginBottom: spacing.lg }}>
        {stats.scans_7d > 0
          ? `${stats.scans_7d} sheet${stats.scans_7d === 1 ? '' : 's'} scanned this week.`
          : 'No sheets scanned in the last 7 days.'}
      </Txt>

      {/* Scanning is the job this app exists for, so it is the first action. */}
      <Card style={{ backgroundColor: colors.primary, borderColor: colors.border, marginBottom: spacing.lg }}>
        <Txt variant="heading" weight="bold" color={colors.primaryForeground}>
          Scan an answer sheet
        </Txt>
        <Txt variant="small" color={colors.primaryForeground}
             style={{ opacity: 0.9, marginTop: 4, marginBottom: spacing.lg }}>
          Photograph or upload an OMR sheet. It is read, matched to the test's
          answer key and scored automatically.
        </Txt>
        <Button title="Start scanning" variant="secondary"
                icon={<ScanIcon size={18} color={colors.secondaryForeground}
                                documentColor="#FFFFFF" lineColor={colors.secondary} />}
                onPress={() => navigation.navigate('Scan')} fullWidth />
      </Card>

      <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.sm }}>
        <Stat label="Tests" value={stats.tests} />
        <Stat label="Sheets" value={stats.scans} />
        <Stat label="Reports" value={stats.reports} />
      </View>
      <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.xl }}>
        <Stat label="Evaluated" value={stats.completed} tone={colors.success} />
        <Stat label="Failed" value={stats.failed}
              tone={stats.failed > 0 ? colors.destructive : undefined} />
        <Stat label="Average" value={avg === null ? '—' : `${avg.toFixed(1)}%`}
              tone={colors.primary} />
      </View>

      <SectionHeader
        title="Recent activity"
        subtitle="The last five sheets you processed"
        action={
          <Button title="History" variant="ghost" size="sm"
                  onPress={() => navigation.navigate('History')} />
        }
      />
      {recent.length === 0 ? (
        <Card style={{ marginBottom: spacing.xl }}>
          <Txt variant="small" muted center>
            Nothing scanned yet. Create a test, add its answer key, then scan a sheet.
          </Txt>
        </Card>
      ) : (
        <View style={{ gap: spacing.sm, marginBottom: spacing.xl }}>
          {recent.map((r) => (
            <Card
              key={r.submission_id}
              padded={false}
              onPress={() => navigation.navigate('Result', { submissionId: r.submission_id })}
              style={{ padding: spacing.md }}
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.md }}>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Txt weight="semibold" numberOfLines={1}>
                    {r.student_name || r.roll_no || `Sheet #${r.submission_id}`}
                  </Txt>
                  <Txt variant="caption" muted numberOfLines={1} style={{ marginTop: 2 }}>
                    {r.test_name}
                  </Txt>
                </View>
                {r.status === 'completed' ? (
                  <View style={{ alignItems: 'flex-end' }}>
                    <Txt weight="bold" color={colors.primary}>
                      {num(r.percentage).toFixed(1)}%
                    </Txt>
                    <Txt variant="caption" muted>
                      {num(r.total_marks)}/{num(r.max_marks)}
                    </Txt>
                  </View>
                ) : (
                  <Badge label={r.status} tone={statusTone(r.status)} small />
                )}
              </View>
            </Card>
          ))}
        </View>
      )}

      {byTest.some((t) => t.evaluated > 0) && (
        <>
          <SectionHeader title="Performance by test" subtitle="Average across evaluated sheets" />
          <Card style={{ marginBottom: spacing.xl }}>
            {byTest.filter((t) => t.evaluated > 0).map((t, i, arr) => {
              const a = num(t.avg_percentage);
              return (
                <View key={t.id} style={{ marginBottom: i === arr.length - 1 ? 0 : spacing.md }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 5 }}>
                    <Txt variant="small" weight="semibold" numberOfLines={1} style={{ flex: 1 }}>
                      {t.name}
                    </Txt>
                    <Txt variant="small" weight="bold" color={colors.primary}>
                      {a.toFixed(1)}%
                    </Txt>
                  </View>
                  <MiniBar segments={[
                    { value: a, color: colors.primary },
                    { value: Math.max(0, 100 - a), color: colors.muted },
                  ]} height={8} />
                  <Txt variant="caption" muted style={{ marginTop: 3 }}>
                    {t.evaluated} evaluated · best {num(t.best_percentage).toFixed(1)}%
                  </Txt>
                </View>
              );
            })}
          </Card>
        </>
      )}

      <SectionHeader title="Quick actions" />
      <Card padded={false} style={{ padding: spacing.md }}>
        <Row label="Tests" value={`${stats.tests} created`} />
        <Row label="Answer keys" value="Create or edit" />
        <Row label="Reports" value={`${stats.reports} generated`} last />
        <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md }}>
          <Button title="Tests" variant="outline" size="sm" style={{ flex: 1 }}
                  onPress={() => navigation.navigate('Tests')} />
          <Button title="Results" variant="outline" size="sm" style={{ flex: 1 }}
                  onPress={() => navigation.navigate('History')} />
          <Button title="Reports" variant="outline" size="sm" style={{ flex: 1 }}
                  onPress={() => navigation.navigate('Reports')} />
        </View>
      </Card>
    </ScrollView>
  );
}
