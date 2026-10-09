import { useMemo } from 'react';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useWindowDimensions } from 'react-native';

import { spacing } from '../theme';

/**
 * Height of the floating tab bar's own pill (icon row + vertical padding),
 * excluding the device inset and the gap it floats above that inset.
 * Kept in sync with FloatingTabBar.tsx by hand: both read off the same
 * Figma-style spec (6px top/bottom padding around a ~30px icon row).
 */
export const TAB_BAR_PILL = 46;
/** Gap between the floating bar and the bottom of the screen/inset. */
export const TAB_BAR_FLOAT_GAP = 10;

/**
 * Padding and sizing that adapt to the actual device.
 *
 * Screens used fixed numbers (`spacing.xxl * 2`) for their bottom padding,
 * which happened to clear the old fixed-height tab bar and nothing else: on
 * a phone with a gesture bar the last row sat underneath it, and on a device
 * with no inset there was a band of dead space.
 */
export function useScreenInsets() {
    const insets = useSafeAreaInsets();
    const { width, height } = useWindowDimensions();

    return useMemo(() => {
        // Space the floating bar actually occupies above the screen's bottom
        // edge: its own pill height, plus the gap it floats above the inset,
        // plus the inset itself. The bar is absolutely positioned (it does
        // not push the tab navigator's content area), so scroll content must
        // reserve this space itself or the last row sits underneath it.
        const tabBar = TAB_BAR_PILL + TAB_BAR_FLOAT_GAP + Math.max(insets.bottom, 10);
        // Narrow phones (<360dp, e.g. a small Android) need tighter gutters
        // or cards lose too much width to padding.
        const gutter = width < 360 ? spacing.md : spacing.lg;

        return {
            insets,
            width,
            height,
            isNarrow: width < 360,
            isTablet: width >= 768,
            gutter,
            /** Top padding for a screen that draws its own header. */
            top: insets.top + spacing.md,
            /** Bottom padding for a scroll view inside the tab navigator. */
            scrollBottom: tabBar + spacing.lg,
            /** Bottom padding for a screen pushed over the tabs (no tab bar). */
            stackBottom: Math.max(insets.bottom, spacing.md) + spacing.lg,
            /** Height the tab bar occupies, for absolutely-positioned footers. */
            tabBar,
        };
    }, [insets, width, height]);
}
