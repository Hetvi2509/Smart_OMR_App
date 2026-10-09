import React, { useState } from 'react';
import { FlatList, RefreshControl, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useScreenInsets } from '../hooks/useScreenInsets';

import { endpoints } from '../api/endpoints';
import { ReportMeta } from '../api/types';
import { useApi } from '../hooks/useApi';
import { openReportPdf } from '../lib/reportFile';
import { spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import {
  Button, Card, EmptyState, ErrorState, Txt, useToast,
} from '../ui';
import { ListSkeleton } from '../ui/skeleton';

export default function ReportsScreen({ navigation }: any) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const screen = useScreenInsets();
  const toast = useToast();
  const [busyId, setBusyId] = useState<number | null>(null);

  const { data, error, loading, refreshing, refresh, reload } =
    useApi(() => endpoints.listReports(), [], { key: 'reports' });

  const open = async (report: ReportMeta) => {
    setBusyId(report.id);
    try {
      const shared = await openReportPdf(report.id);
      if (!shared) toast.show('Report saved to this device.', 'success');
    } catch (err) {
      toast.show((err as Error).message, 'error');
    } finally {
      setBusyId(null);
    }
  };

  if (loading && !data) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.background, padding: spacing.lg, paddingTop: screen.top }}>
        <ListSkeleton />
      </View>
    );
  }
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;

  const reports = data?.reports ?? [];

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <FlatList
        data={reports}
        keyExtractor={(r) => String(r.id)}
        contentContainerStyle={{
          padding: spacing.lg,
          paddingTop: screen.top,
          paddingBottom: screen.scrollBottom,
          flexGrow: 1,
        }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={refresh}
                          tintColor={colors.primary} />
        }
        ListHeaderComponent={
          <View style={{ marginBottom: spacing.md }}>
            <Txt variant="display" weight="bold">Reports</Txt>
            <Txt variant="small" muted style={{ marginTop: 2 }}>
              Every generated result sheet, newest first.
            </Txt>
          </View>
        }
        ListEmptyComponent={
          <EmptyState
            icon="⎙"
            title="No reports yet"
            body="Open an evaluated sheet and tap Generate report to produce a printable PDF."
            action={<Button title="Go to history" onPress={() => navigation.navigate('History')} />}
          />
        }
        renderItem={({ item }) => (
          <Card>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.md }}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Txt weight="bold" numberOfLines={1}>
                  {item.student_name || item.roll_no || `Sheet #${item.submission_id}`}
                </Txt>
                <Txt variant="caption" muted numberOfLines={1} style={{ marginTop: 2 }}>
                  {item.test_name || 'Test'} ·{' '}
                  {item.file_size ? `${Math.round(item.file_size / 1024)} KB` : 'PDF'}
                </Txt>
                <Txt variant="caption" muted style={{ marginTop: 2 }}>
                  {new Date(item.created_at).toLocaleString()}
                </Txt>
              </View>
              <Button
                title="Open"
                size="sm"
                variant="outline"
                loading={busyId === item.id}
                onPress={() => open(item)}
              />
            </View>
            {!!item.submission_id && (
              <Button
                title="View full result"
                variant="ghost"
                size="sm"
                style={{ marginTop: spacing.sm }}
                onPress={() => navigation.navigate('Result', { submissionId: item.submission_id })}
              />
            )}
          </Card>
        )}
        ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
      />
    </View>
  );
}
