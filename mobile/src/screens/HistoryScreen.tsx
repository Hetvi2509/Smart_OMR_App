import React, { useMemo, useState } from 'react';
import { FlatList, RefreshControl, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useScreenInsets } from '../hooks/useScreenInsets';

import { endpoints } from '../api/endpoints';
import { HistoryRow, num } from '../api/types';
import { useApi } from '../hooks/useApi';
import { spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import ScanIcon from '../ui/icons/ScanIcon';
import {
  Badge, Button, Card, EmptyState, ErrorState, Field, Loading, Segmented, Txt,
  statusTone,
} from '../ui';
import { ListSkeleton } from '../ui/skeleton';

const SORTS = [
  { value: 'recent', label: 'Newest' },
  { value: 'oldest', label: 'Oldest' },
  { value: 'score_high', label: 'Top score' },
  { value: 'score_low', label: 'Low score' },
  { value: 'name', label: 'Name' },
  { value: 'roll', label: 'Roll no.' },
];

const STATUSES = [
  { value: '', label: 'All' },
  { value: 'completed', label: 'Evaluated' },
  { value: 'failed', label: 'Failed' },
];

export default function HistoryScreen({ route, navigation }: any) {
  const presetTestId: number | undefined = route.params?.testId;
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const screen = useScreenInsets();

  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('recent');
  const [status, setStatus] = useState('');

  // Sorting and filtering run on the server so they apply to the whole
  // history, not just the page already downloaded.
  const { data, error, loading, refreshing, refresh, reload } = useApi(
    () => endpoints.listResults({
      sort, status: status || undefined, test_id: presetTestId, limit: 200,
    }),
    [sort, status, presetTestId],
    // Keyed by the filters, so switching back to a previous view is instant.
    { key: `results:${sort}:${status}:${presetTestId ?? ''}` },
  );

  const rows = useMemo(() => {
    const all = data?.results ?? [];
    const term = search.trim().toLowerCase();
    if (!term) return all;
    // Local narrowing on top of the server query, so typing feels instant.
    return all.filter((r) =>
      (r.student_name || '').toLowerCase().includes(term) ||
      (r.roll_no || '').toLowerCase().includes(term) ||
      r.test_name.toLowerCase().includes(term));
  }, [data, search]);

  if (loading && !data) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.background, padding: spacing.lg, paddingTop: screen.top }}>
        <ListSkeleton />
      </View>
    );
  }
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <FlatList
        data={rows}
        keyExtractor={(r) => String(r.submission_id)}
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
            <Txt variant="display" weight="bold">History</Txt>
            <Txt variant="small" muted style={{ marginTop: 2, marginBottom: spacing.lg }}>
              {data?.total ?? 0} sheet{(data?.total ?? 0) === 1 ? '' : 's'} processed
              {presetTestId ? ' for this test' : ''}
            </Txt>
            <Field value={search} onChangeText={setSearch}
                   placeholder="Search name, roll number or test"
                   autoCapitalize="none" style={{ marginBottom: spacing.md }} />
            <Segmented options={STATUSES} value={status} onChange={setStatus} />
            <Segmented options={SORTS} value={sort} onChange={setSort} />
          </View>
        }
        ListEmptyComponent={
          search || status ? (
            <EmptyState icon="⌕" title="Nothing matches"
                        body="Try a different search term or filter." />
          ) : (
            <EmptyState
              icon="⌸"
              title="No sheets yet"
              body="Scanned sheets and their results appear here, with everything stored in the database."
              action={<Button title="Scan a sheet"
                              icon={<ScanIcon size={16} color={colors.primaryForeground}
                                              documentColor="#FFFFFF" lineColor={colors.primary} />}
                              onPress={() => navigation.navigate('Scan')} />}
            />
          )
        }
        renderItem={({ item }) => (
          <HistoryCard
            row={item}
            onPress={() => navigation.navigate('Result', { submissionId: item.submission_id })}
          />
        )}
        ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
      />
    </View>
  );
}

function HistoryCardBase({ row, onPress }: { row: HistoryRow; onPress: () => void }) {
  const { colors } = useTheme();
  const done = row.status === 'completed';
  const pct = num(row.percentage);

  return (
    <Card onPress={onPress}>
      <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md }}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Txt weight="bold" numberOfLines={1}>
            {row.student_name || row.roll_no || `Sheet #${row.submission_id}`}
          </Txt>
          <Txt variant="caption" muted numberOfLines={1} style={{ marginTop: 2 }}>
            {row.test_name}
            {row.class_std ? ` · Class ${row.class_std}` : ''}
            {row.section ? `-${row.section}` : ''}
          </Txt>
          <Txt variant="caption" muted style={{ marginTop: 2 }}>
            {new Date(row.created_at).toLocaleString()}
          </Txt>
        </View>

        {done ? (
          <View style={{ alignItems: 'flex-end' }}>
            <Txt variant="title" weight="bold" color={colors.primary}>
              {pct.toFixed(1)}%
            </Txt>
            <Txt variant="caption" muted>
              {num(row.total_marks)}/{num(row.max_marks)}
            </Txt>
            {!!row.grade && <Badge label={row.grade} tone={pct >= 60 ? 'success' : pct >= 40 ? 'warning' : 'danger'} small />}
          </View>
        ) : (
          <Badge label={row.status} tone={statusTone(row.status)} small />
        )}
      </View>

      {done && (
        <View style={{ flexDirection: 'row', gap: spacing.lg, marginTop: spacing.md }}>
          <Metric label="Correct" value={row.correct_count ?? 0} color={colors.success} />
          <Metric label="Wrong" value={row.wrong_count ?? 0} color={colors.destructive} />
          <Metric label="Blank" value={row.unattempted_count ?? 0} color={colors.mutedForeground} />
          {(row.review_questions?.length ?? 0) > 0 && (
            <Metric label="Review" value={row.review_questions.length} color={colors.accent} />
          )}
        </View>
      )}

      {row.status === 'failed' && !!row.error_hint && (
        <Txt variant="caption" color={colors.destructive} style={{ marginTop: spacing.sm }}
             numberOfLines={2}>
          {row.error_hint}
        </Txt>
      )}
    </Card>
  );
}

function MetricBase({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <View>
      <Txt variant="caption" muted>{label.toUpperCase()}</Txt>
      <Txt variant="small" weight="bold" color={color}>{value}</Txt>
    </View>
  );
}

// Memoised: a long list re-renders every row whenever the screen's own
// state changes, and these rows are pure functions of their props.
const HistoryCard = React.memo(HistoryCardBase);

// Memoised: a long list re-renders every row whenever the screen's own
// state changes, and these rows are pure functions of their props.
const Metric = React.memo(MetricBase);
