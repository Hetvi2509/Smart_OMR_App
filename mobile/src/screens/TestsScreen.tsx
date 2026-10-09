import React, { useState } from 'react';
import { FlatList, RefreshControl, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useScreenInsets } from '../hooks/useScreenInsets';

import { endpoints } from '../api/endpoints';
import { Test } from '../api/types';
import { useApi } from '../hooks/useApi';
import { spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import {
  Badge, Button, Card, EmptyState, ErrorState, Field, Txt, statusTone,
} from '../ui';
import { ListSkeleton } from '../ui/skeleton';

export default function TestsScreen({ navigation }: any) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const screen = useScreenInsets();
  const [search, setSearch] = useState('');
  const { data, error, loading, refreshing, refresh, reload } =
    useApi(() => endpoints.listTests(), [], { key: 'tests' });

  if (loading && !data) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.background, padding: spacing.lg, paddingTop: screen.top }}>
        <ListSkeleton />
      </View>
    );
  }
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;

  const all = data?.tests ?? [];
  const term = search.trim().toLowerCase();
  const tests = term
    ? all.filter((t) =>
        t.name.toLowerCase().includes(term) ||
        (t.subject || '').toLowerCase().includes(term))
    : all;

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <FlatList
        data={tests}
        keyExtractor={(t) => String(t.id)}
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
            <Txt variant="display" weight="bold">Tests</Txt>
            <Txt variant="small" muted style={{ marginTop: 2, marginBottom: spacing.lg }}>
              Each test holds its own answer key and marking scheme.
            </Txt>
            <Button title="New test" onPress={() => navigation.navigate('EditTest', {})}
                    fullWidth />
            {all.length > 3 && (
              <View style={{ marginTop: spacing.lg }}>
                <Field value={search} onChangeText={setSearch}
                       placeholder="Search tests" autoCapitalize="none"
                       style={{ marginBottom: 0 }} />
              </View>
            )}
          </View>
        }
        ListEmptyComponent={
          term ? (
            <EmptyState icon="⌕" title="No matching tests"
                        body={`Nothing matches "${search}".`} />
          ) : (
            <EmptyState
              icon="≡"
              title="No tests yet"
              body="Create a test to describe the exam: its sheet layout, question count and marking scheme."
              action={<Button title="Create the first test"
                              onPress={() => navigation.navigate('EditTest', {})} />}
            />
          )
        }
        renderItem={({ item }) => <TestCard test={item} navigation={navigation} />}
        ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
      />
    </View>
  );
}

function TestCardBase({ test, navigation }: { test: Test; navigation: any }) {
  const { colors } = useTheme();
  const keyCount = test.key_count ?? 0;
  const ready = keyCount > 0;

  return (
    <Card onPress={() => navigation.navigate('TestDetail', { testId: test.id })}>
      <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md }}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Txt variant="heading" weight="bold" numberOfLines={2}>{test.name}</Txt>
          <Txt variant="small" muted style={{ marginTop: 3 }} numberOfLines={1}>
            {[test.subject, test.layout.toUpperCase(),
              `${test.total_questions} questions`].filter(Boolean).join(' · ')}
          </Txt>
        </View>
        <Badge label={ready ? 'Ready' : 'Draft'}
               tone={ready ? 'success' : 'muted'} small />
      </View>

      <View style={{ flexDirection: 'row', gap: spacing.lg, marginTop: spacing.md }}>
        <View>
          <Txt variant="caption" muted>ANSWER KEY</Txt>
          <Txt variant="small" weight="bold"
               color={ready ? colors.success : colors.destructive}>
            {ready ? `${keyCount} answers` : 'Not added'}
          </Txt>
        </View>
        <View>
          <Txt variant="caption" muted>SHEETS</Txt>
          <Txt variant="small" weight="bold">{test.submission_count ?? 0}</Txt>
        </View>
        <View>
          <Txt variant="caption" muted>MARKING</Txt>
          <Txt variant="small" weight="bold">
            +{test.marks_correct} / {test.marks_wrong}
          </Txt>
        </View>
      </View>

      {!ready && (
        <Button
          title="Add answer key"
          size="sm"
          variant="outline"
          style={{ marginTop: spacing.md }}
          onPress={() => navigation.navigate('AnswerKey', { testId: test.id })}
        />
      )}
    </Card>
  );
}

// Memoised: a long list re-renders every row whenever the screen's own
// state changes, and these rows are pure functions of their props.
const TestCard = React.memo(TestCardBase);
