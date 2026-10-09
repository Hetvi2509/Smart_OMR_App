/**
 * Shimmer skeletons.
 *
 * Every screen's first load costs about a second of pure network latency to
 * the database (a fixed physical round-trip, not something client code can
 * remove — see useApi's cache for the actual fix on repeat visits). A blank
 * spinner for that second reads as "slow"; placeholder shapes the size of
 * the real content read as "loading", because the layout is already there.
 */
import React, { useEffect, useRef } from 'react';
import { Animated, Easing, View, ViewStyle } from 'react-native';

import { radius, spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import { Card } from './index';

function useShimmer() {
  const value = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(value, {
          toValue: 1, duration: 850, easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(value, {
          toValue: 0, duration: 850, easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [value]);
  return value;
}

/** A single shimmering block. The building unit every skeleton below uses. */
export function Bone({ width, height = 14, radius: r = 6, style }: {
  width: number | `${number}%`; height?: number; radius?: number;
  style?: ViewStyle;
}) {
  const { colors } = useTheme();
  const shimmer = useShimmer();
  const opacity = shimmer.interpolate({ inputRange: [0, 1], outputRange: [0.35, 0.75] });
  return (
    <Animated.View
      style={[
        { width, height, borderRadius: r, backgroundColor: colors.muted, opacity },
        style,
      ]}
    />
  );
}

/** One stat tile, matching <Stat> in ui/index.tsx. */
export function StatSkeleton({ flex = 1 }: { flex?: number }) {
  return (
    <Card style={{ flex, padding: spacing.md, minWidth: 0 }}>
      <Bone width="70%" height={9} radius={4} />
      <Bone width="50%" height={20} radius={4} style={{ marginTop: 8 }} />
    </Card>
  );
}

/** A card-shaped row, matching the list cards in Tests/History/Reports. */
export function RowCardSkeleton() {
  return (
    <Card>
      <View style={{ flexDirection: 'row', gap: spacing.md }}>
        <View style={{ flex: 1, gap: 8 }}>
          <Bone width="65%" height={15} />
          <Bone width="40%" height={11} />
        </View>
        <Bone width={56} height={24} radius={radius.pill} />
      </View>
    </Card>
  );
}

export function DashboardSkeleton() {
  return (
    <View>
      <Bone width="45%" height={13} />
      <Bone width="65%" height={30} style={{ marginTop: 8 }} />
      <Bone width="80%" height={13} style={{ marginTop: 8, marginBottom: spacing.lg }} />

      <Card style={{ backgroundColor: undefined, marginBottom: spacing.lg }}>
        <Bone width="60%" height={17} />
        <Bone width="90%" height={13} style={{ marginTop: 8 }} />
        <Bone width="100%" height={48} radius={radius.md} style={{ marginTop: spacing.lg }} />
      </Card>

      <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.sm }}>
        <StatSkeleton /><StatSkeleton /><StatSkeleton />
      </View>
      <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.xl }}>
        <StatSkeleton /><StatSkeleton /><StatSkeleton />
      </View>

      <Bone width="35%" height={17} style={{ marginBottom: spacing.md }} />
      <View style={{ gap: spacing.sm }}>
        <RowCardSkeleton /><RowCardSkeleton /><RowCardSkeleton />
      </View>
    </View>
  );
}

export function ListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <View style={{ gap: spacing.sm }}>
      {Array.from({ length: count }, (_, i) => <RowCardSkeleton key={i} />)}
    </View>
  );
}

/** The result screen's score card plus a few question rows. */
export function ResultSkeleton() {
  return (
    <View>
      <Bone width="40%" height={13} />
      <Bone width="70%" height={28} style={{ marginTop: 6, marginBottom: spacing.lg }} />
      <Card style={{ marginBottom: spacing.lg }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <View>
            <Bone width={110} height={11} />
            <Bone width={90} height={32} style={{ marginTop: 6 }} />
          </View>
          <Bone width={70} height={24} radius={radius.pill} />
        </View>
        <Bone width="100%" height={10} radius={radius.pill} style={{ marginTop: spacing.lg }} />
      </Card>
      <Card padded={false} style={{ padding: spacing.md }}>
        {[0, 1, 2, 3].map((i) => (
          <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 10 }}>
            <Bone width="45%" height={12} />
            <Bone width="25%" height={12} />
          </View>
        ))}
      </Card>
    </View>
  );
}
