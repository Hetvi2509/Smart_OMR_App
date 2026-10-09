/**
 * Line icons for the tab bar, matching ScanIcon's stroke weight so every tab
 * sits on the same visual baseline. The previous glyphs (◧ ≡ ⌸ ⎙ ⚙) came
 * from font metrics that differ per character -- each one has a different
 * optical size and baseline, which is what produced the misaligned row in
 * the floating bar. A shared 24x24 viewBox with a fixed stroke width fixes
 * that at the source instead of patching it with per-icon offsets.
 */
import React from 'react';
import Svg, { Circle, Path, Rect } from 'react-native-svg';

type IconProps = { size?: number; color: string; strokeWidth?: number };

export function HomeIcon({ size = 22, color, strokeWidth = 2 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path d="M3 10.5 12 3l9 7.5" stroke={color} strokeWidth={strokeWidth}
            strokeLinecap="round" strokeLinejoin="round" />
      <Path d="M5 9.5V20a1 1 0 0 0 1 1h4v-5.5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1V21h4a1 1 0 0 0 1-1V9.5"
            stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function TestsIcon({ size = 22, color, strokeWidth = 2 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Rect x={4} y={3} width={16} height={18} rx={2} stroke={color} strokeWidth={strokeWidth} />
      <Path d="M8 8h8M8 12h8M8 16h5" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" />
    </Svg>
  );
}

export function HistoryIcon({ size = 22, color, strokeWidth = 2 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path d="M3 12a9 9 0 1 0 3-6.7" stroke={color} strokeWidth={strokeWidth}
            strokeLinecap="round" strokeLinejoin="round" />
      <Path d="M3 4v4.5h4.5" stroke={color} strokeWidth={strokeWidth}
            strokeLinecap="round" strokeLinejoin="round" />
      <Path d="M12 8v4.5l3 2" stroke={color} strokeWidth={strokeWidth}
            strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function ReportsIcon({ size = 22, color, strokeWidth = 2 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path d="M12 3v12m0 0-4-4m4 4 4-4" stroke={color} strokeWidth={strokeWidth}
            strokeLinecap="round" strokeLinejoin="round" />
      <Path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" stroke={color}
            strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function ProfileIcon({ size = 22, color, strokeWidth = 2 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Circle cx={12} cy={8} r={3.5} stroke={color} strokeWidth={strokeWidth} />
      <Path d="M4.5 20a7.5 7.5 0 0 1 15 0" stroke={color} strokeWidth={strokeWidth}
            strokeLinecap="round" />
    </Svg>
  );
}
