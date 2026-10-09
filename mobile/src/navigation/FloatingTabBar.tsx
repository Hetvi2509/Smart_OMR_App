/**
 * A floating, rounded bottom navigation bar: the bar is inset from the
 * screen edges with its own shadow rather than running edge-to-edge, and the
 * active tab gets a sliding pill behind its icon+label instead of a plain
 * colour change. This is the common "mobile nav bar" shape in current
 * design-community references (rounded floating card, animated active
 * indicator, icon+label pairs) rather than a flat edge-to-edge bar.
 */
import { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import React, { useEffect, useRef } from 'react';
import { Animated, Platform, Pressable, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { TAB_BAR_PILL } from '../hooks/useScreenInsets';
import { fonts, radius, shadow, spacing } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import { Txt } from '../ui';
import ScanIcon from '../ui/icons/ScanIcon';
import {
  HistoryIcon, HomeIcon, ProfileIcon, ReportsIcon, TestsIcon,
} from '../ui/icons/TabIcons';

const ICON_FOR: Record<string, React.ComponentType<{ size?: number; color: string }>> = {
  Dashboard: HomeIcon, Tests: TestsIcon, History: HistoryIcon,
  Reports: ReportsIcon, Profile: ProfileIcon,
};
const LABELS: Record<string, string> = {
  Dashboard: 'Home', Tests: 'Tests', Scan: 'Scan',
  History: 'History', Reports: 'Reports', Profile: 'Profile',
};

// A row 24px tall holds every icon or the Scan circle, whichever is shown --
// this is what the previous version lacked: each tab sized its own icon with
// no shared box, so a wide glyph like "≡" sat at a different height than a
// narrow one like "◧". A fixed box makes every tab's icon occupy the same
// footprint regardless of what it draws inside it.
const ICON_BOX = 26;

export default function FloatingTabBar({ state, descriptors, navigation }: BottomTabBarProps) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();

  // The bar floats above the home indicator / gesture bar rather than
  // butting against it, which is the visual signature of this style; on a
  // device with no inset it still keeps a comfortable minimum gap.
  const bottomGap = Math.max(insets.bottom, 10);

  // An explicit height on the absolutely-positioned wrapper, rather than
  // letting it size from its content: on web, `pointerEvents="box-none"` on
  // an auto-height flex container did not reliably let clicks pass through
  // the empty margin above the bar, and intercepted touches on whatever
  // screen content happened to sit underneath that region.
  const wrapperHeight = TAB_BAR_PILL + bottomGap;

  return (
    <View
      pointerEvents="box-none"
      style={{
        position: 'absolute', left: spacing.md, right: spacing.md,
        bottom: 0, height: wrapperHeight,
        alignItems: 'center', justifyContent: 'flex-end',
        paddingBottom: bottomGap,
      }}
    >
      <View
        style={[
          {
            flexDirection: 'row',
            alignItems: 'center',
            backgroundColor: colors.card,
            borderRadius: radius.pill,
            borderWidth: 1.5,
            borderColor: colors.border,
            paddingVertical: 6,
            paddingHorizontal: 6,
            width: '100%',
            maxWidth: 480,
          },
          shadow.raised,
          // Android's shadow prop needs elevation set directly on this view
          // (the shared `shadow.raised` token covers it, kept here as the
          // single place this bar's own elevation could be tuned).
          Platform.OS === 'android' ? { elevation: 10 } : null,
        ]}
      >
        {state.routes.map((route, index) => {
          const { options } = descriptors[route.key];
          const focused = state.index === index;
          const label = (options.tabBarLabel as string) ?? LABELS[route.name] ?? route.name;

          const onPress = () => {
            const event = navigation.emit({
              type: 'tabPress', target: route.key, canPreventDefault: true,
            });
            if (!focused && !event.defaultPrevented) {
              navigation.navigate(route.name);
            }
          };

          return (
            <TabButton
              key={route.key}
              routeName={route.name}
              label={label}
              focused={focused}
              onPress={onPress}
              onLongPress={() => navigation.emit({ type: 'tabLongPress', target: route.key })}
            />
          );
        })}
      </View>
    </View>
  );
}

function TabButton({
  routeName, label, focused, onPress, onLongPress,
}: {
  routeName: string; label: string; focused: boolean;
  onPress: () => void; onLongPress: () => void;
}) {
  const { colors } = useTheme();
  const anim = useRef(new Animated.Value(focused ? 1 : 0)).current;

  useEffect(() => {
    Animated.spring(anim, {
      toValue: focused ? 1 : 0, useNativeDriver: false,
      friction: 9, tension: 80,
    }).start();
  }, [focused, anim]);

  // Scan is the primary action: it keeps a filled circle even when inactive,
  // the same treatment it had before, now inside the floating bar.
  const isScan = routeName === 'Scan';
  const Icon = ICON_FOR[routeName];

  const pillBg = anim.interpolate({
    inputRange: [0, 1],
    outputRange: ['rgba(0,0,0,0)', `${colors.primary}1A`],
  });
  const scale = anim.interpolate({ inputRange: [0, 1], outputRange: [1, 1.04] });
  const iconColor = focused ? colors.primary : colors.mutedForeground;

  return (
    <Pressable
      onPress={onPress}
      onLongPress={onLongPress}
      accessibilityRole="button"
      accessibilityState={{ selected: focused }}
      accessibilityLabel={label}
      // Removes the browser's default focus ring on a clicked button, which
      // on web drew a white rectangle above the tab's icon -- it looked like
      // a layout bug but was the platform's own outline, not app content.
      style={({ pressed }) => [
        { flex: 1, opacity: pressed ? 0.85 : 1 },
        Platform.OS === 'web' ? ({ outlineWidth: 0, outlineStyle: 'none' } as any) : null,
      ]}
    >
      <Animated.View
        style={{
          // Stacked, not side-by-side: six tabs with always-visible labels
          // need a layout that still fits a 360dp phone. "Reports" next to
          // its icon does not; "Reports" under a 22px icon does.
          alignItems: 'center',
          justifyContent: 'center',
          gap: 3,
          paddingVertical: 7,
          borderRadius: radius.md,
          backgroundColor: pillBg,
          transform: [{ scale }],
        }}
      >
        {/* Every tab's icon sits in the same fixed box, so the row reads as
            one aligned line regardless of which icon or the Scan circle is
            inside it. */}
        <View style={{ width: ICON_BOX, height: ICON_BOX, alignItems: 'center', justifyContent: 'center' }}>
          {isScan ? (
            <View
              style={{
                width: ICON_BOX, height: ICON_BOX, borderRadius: radius.pill,
                backgroundColor: focused ? colors.primary : colors.secondary,
                alignItems: 'center', justifyContent: 'center',
              }}
            >
              <ScanIcon
                size={16}
                color={colors.primaryForeground}
                documentColor={colors.primaryForeground}
                lineColor={focused ? colors.primary : colors.secondary}
              />
            </View>
          ) : Icon ? (
            <Icon size={21} color={iconColor} />
          ) : null}
        </View>
        {/* The label is always shown -- an icon-only inactive tab would be
            unreadable without it, since nothing here is a widely recognised
            pictogram the way a phone or search icon is. */}
        <Txt
          variant="caption"
          weight={focused ? 'bold' : 'medium'}
          color={focused ? colors.primary : colors.mutedForeground}
          numberOfLines={1}
          style={{ fontFamily: focused ? fonts.semibold : fonts.medium, lineHeight: 13 }}
        >
          {label}
        </Txt>
      </Animated.View>
    </Pressable>
  );
}
