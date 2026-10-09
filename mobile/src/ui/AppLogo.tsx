import React from 'react';
import { Image } from 'react-native';

import { radius } from '../theme';
import { useTheme } from '../theme/ThemeProvider';

/**
 * The app's mark, shown on the auth screens and the splash screen.
 *
 * One shared component rather than copy-pasted <Image> blocks, so the
 * logo's framing (size, corner radius, border) stays identical everywhere
 * it appears and only needs changing in one place.
 */
export default function AppLogo({ size = 66 }: { size?: number }) {
  const { colors } = useTheme();
  return (
    <Image
      source={require('../../assets/icon.png')}
      accessibilityLabel="Smart OMR Evaluator"
      style={{
        width: size,
        height: size,
        borderRadius: radius.lg,
        borderWidth: 1.5,
        borderColor: colors.border,
        backgroundColor: colors.card,
      }}
      resizeMode="contain"
    />
  );
}
