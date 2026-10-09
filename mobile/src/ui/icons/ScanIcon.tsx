/**
 * The document-scan icon: four corner brackets framing a document, with a
 * horizontal scan line crossing it. Matches the reference icon the user
 * supplied, redrawn as a scalable vector so it renders crisply at any size
 * and can be recoloured per theme instead of shipping a fixed-colour PNG.
 */
import React from 'react';
import Svg, { Path, Rect } from 'react-native-svg';

type Props = {
  size?: number;
  /** Colour of the corner brackets and the scan line. */
  color?: string;
  /** Fill of the document card behind them. */
  documentColor?: string;
  /** Colour of the text lines drawn on the document. */
  lineColor?: string;
};

export default function ScanIcon({
  size = 24,
  color = '#1C9BE6',
  documentColor = '#E8ECEF',
  lineColor = '#5B6B77',
}: Props) {
  return (
    <Svg width={size} height={size} viewBox="0 0 512 512" fill="none">
      {/* the document card */}
      <Rect x={146} y={104} width={220} height={304} rx={16} fill={documentColor} />
      {/* text lines on the document */}
      <Rect x={178} y={152} width={156} height={16} rx={8} fill={lineColor} />
      <Rect x={178} y={196} width={156} height={16} rx={8} fill={lineColor} />
      <Rect x={178} y={296} width={156} height={16} rx={8} fill={lineColor} />
      <Rect x={178} y={340} width={156} height={16} rx={8} fill={lineColor} />
      {/* the scan line crossing the document */}
      <Rect x={72} y={238} width={368} height={36} rx={18} fill={color} />
      {/* four corner brackets */}
      <Path
        d="M32 112V72a40 40 0 0 1 40-40h40"
        stroke={color} strokeWidth={36} strokeLinecap="round" fill="none"
      />
      <Path
        d="M400 32h40a40 40 0 0 1 40 40v40"
        stroke={color} strokeWidth={36} strokeLinecap="round" fill="none"
      />
      <Path
        d="M480 400v40a40 40 0 0 1-40 40h-40"
        stroke={color} strokeWidth={36} strokeLinecap="round" fill="none"
      />
      <Path
        d="M112 480H72a40 40 0 0 1-40-40v-40"
        stroke={color} strokeWidth={36} strokeLinecap="round" fill="none"
      />
    </Svg>
  );
}
