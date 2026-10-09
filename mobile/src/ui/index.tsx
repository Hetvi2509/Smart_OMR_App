/**
 * The app's UI kit, styled to poppy-1: flat cards with a hard outline,
 * generous radius, almost no shadow.
 */
import React, { useEffect, useRef } from 'react';
import {
  ActivityIndicator, Animated, Modal, Pressable, ScrollView, StyleProp,
  StyleSheet, Text, TextInput, TextInputProps, TextStyle, View, ViewStyle,
} from 'react-native';

import { Colors, fonts, radius, shadow, spacing, type as typo } from '../theme';
import { useTheme } from '../theme/ThemeProvider';

/* ---------------------------------------------------------------- text ---- */

type TxtProps = {
  children: React.ReactNode;
  variant?: keyof typeof typo;
  weight?: 'regular' | 'medium' | 'semibold' | 'bold';
  color?: string;
  muted?: boolean;
  mono?: boolean;
  center?: boolean;
  numberOfLines?: number;
  style?: StyleProp<TextStyle>;
};

export function Txt({
  children, variant = 'body', weight = 'regular', color, muted, mono,
  center, numberOfLines, style,
}: TxtProps) {
  const { colors } = useTheme();
  const family = mono
    ? fonts.mono
    : { regular: fonts.sans, medium: fonts.medium, semibold: fonts.semibold, bold: fonts.bold }[weight];
  return (
    <Text
      numberOfLines={numberOfLines}
      style={[
        typo[variant],
        { fontFamily: family, color: color ?? (muted ? colors.mutedForeground : colors.foreground) },
        center && { textAlign: 'center' },
        style,
      ]}
    >
      {children}
    </Text>
  );
}

/* ---------------------------------------------------------------- card ---- */

export function Card({
  children, style, padded = true, onPress,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  padded?: boolean;
  onPress?: () => void;
}) {
  const { colors, dark } = useTheme();
  const body = (
    <View
      style={[
        {
          backgroundColor: colors.card,
          borderRadius: radius.lg,
          borderWidth: dark ? 1 : 1.5,
          borderColor: colors.border,
          padding: padded ? spacing.lg : 0,
        },
        shadow.card,
        style,
      ]}
    >
      {children}
    </View>
  );
  if (!onPress) return body;
  return (
    <Pressable onPress={onPress} style={({ pressed }) => pressed && { opacity: 0.85, transform: [{ scale: 0.995 }] }}>
      {body}
    </Pressable>
  );
}

export function SectionHeader({
  title, subtitle, action,
}: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <View style={styles.sectionHeader}>
      <View style={{ flex: 1 }}>
        <Txt variant="heading" weight="bold">{title}</Txt>
        {!!subtitle && <Txt variant="small" muted style={{ marginTop: 2 }}>{subtitle}</Txt>}
      </View>
      {action}
    </View>
  );
}

/* -------------------------------------------------------------- button ---- */

type ButtonProps = {
  title: string;
  onPress?: () => void;
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'destructive';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  disabled?: boolean;
  /** A text glyph ("⬛") or a React element (e.g. an SVG icon component). */
  icon?: string | React.ReactNode;
  fullWidth?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function Button({
  title, onPress, variant = 'primary', size = 'md', loading, disabled,
  icon, fullWidth, style,
}: ButtonProps) {
  const { colors } = useTheme();
  const off = disabled || loading;

  const bg = {
    primary: colors.primary,
    secondary: colors.secondary,
    outline: 'transparent',
    ghost: 'transparent',
    destructive: colors.destructive,
  }[variant];
  const fg = {
    primary: colors.primaryForeground,
    secondary: colors.secondaryForeground,
    outline: colors.foreground,
    ghost: colors.primary,
    destructive: colors.destructiveForeground,
  }[variant];
  const height = { sm: 38, md: 48, lg: 56 }[size];

  return (
    <Pressable
      onPress={off ? undefined : onPress}
      disabled={off}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!off, busy: !!loading }}
      style={({ pressed }) => [
        {
          height,
          backgroundColor: bg,
          borderRadius: radius.md,
          borderWidth: variant === 'ghost' ? 0 : 1.5,
          borderColor: variant === 'outline' ? colors.border : bg,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'center',
          paddingHorizontal: size === 'sm' ? spacing.md : spacing.lg,
          gap: spacing.sm,
          opacity: off ? 0.5 : pressed ? 0.88 : 1,
        },
        fullWidth && { alignSelf: 'stretch' },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} size="small" />
      ) : (
        <>
          {!!icon && (typeof icon === 'string'
            ? <Txt color={fg} weight="semibold">{icon}</Txt>
            : icon)}
          <Txt
            weight="semibold"
            color={fg}
            variant={size === 'sm' ? 'small' : 'body'}
          >
            {title}
          </Txt>
        </>
      )}
    </Pressable>
  );
}

/* --------------------------------------------------------------- badge ---- */

export type BadgeTone =
  | 'default' | 'success' | 'warning' | 'danger' | 'info' | 'muted';

export function Badge({
  label, tone = 'default', small,
}: { label: string; tone?: BadgeTone; small?: boolean }) {
  const { colors } = useTheme();
  const map: Record<BadgeTone, string> = {
    default: colors.primary,
    success: colors.success,
    warning: colors.accent,
    danger: colors.destructive,
    info: colors.secondary,
    muted: colors.mutedForeground,
  };
  const base = map[tone];
  return (
    <View
      style={{
        backgroundColor: `${base}22`,
        borderColor: base,
        borderWidth: 1,
        borderRadius: radius.pill,
        paddingHorizontal: small ? 7 : 10,
        paddingVertical: small ? 2 : 4,
        alignSelf: 'flex-start',
      }}
    >
      <Txt variant="caption" weight="bold" color={base}>{label.toUpperCase()}</Txt>
    </View>
  );
}

/** Submission status -> badge tone, used by History, Results and Dashboard. */
export function statusTone(status?: string | null): BadgeTone {
  switch (status) {
    case 'completed': return 'success';
    case 'failed': return 'danger';
    case 'processing': case 'pending': return 'warning';
    case 'ready': return 'info';
    default: return 'muted';
  }
}

/* --------------------------------------------------------------- input ---- */

type FieldProps = TextInputProps & {
  label?: string;
  hint?: string;
  error?: string | null;
  required?: boolean;
};

export function Field({ label, hint, error, required, style, ...rest }: FieldProps) {
  const { colors } = useTheme();
  const [focused, setFocused] = React.useState(false);
  return (
    <View style={{ marginBottom: spacing.lg }}>
      {!!label && (
        <Txt variant="small" weight="semibold" style={{ marginBottom: 6 }}>
          {label}{required ? ' *' : ''}
        </Txt>
      )}
      <TextInput
        placeholderTextColor={colors.mutedForeground}
        onFocus={(e) => { setFocused(true); rest.onFocus?.(e); }}
        onBlur={(e) => { setFocused(false); rest.onBlur?.(e); }}
        style={[
          {
            borderWidth: 1.5,
            borderColor: error ? colors.destructive : focused ? colors.primary : colors.border,
            borderRadius: radius.md,
            backgroundColor: colors.card,
            color: colors.foreground,
            paddingHorizontal: spacing.md,
            paddingVertical: 13,
            fontSize: 15,
            fontFamily: fonts.sans,
          },
          style,
        ]}
        {...rest}
      />
      {!!error && (
        <Txt variant="caption" color={colors.destructive} style={{ marginTop: 5 }}>{error}</Txt>
      )}
      {!error && !!hint && (
        <Txt variant="caption" muted style={{ marginTop: 5 }}>{hint}</Txt>
      )}
    </View>
  );
}

/** A horizontal choice row — used for layouts, sort order and filters. */
export function Segmented<T extends string | number>({
  options, value, onChange, label,
}: {
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (v: T) => void;
  label?: string;
}) {
  const { colors } = useTheme();
  return (
    <View style={{ marginBottom: label ? spacing.lg : 0 }}>
      {!!label && (
        <Txt variant="small" weight="semibold" style={{ marginBottom: 6 }}>{label}</Txt>
      )}
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <View style={{ flexDirection: 'row', gap: spacing.sm }}>
          {options.map((o) => {
            const on = o.value === value;
            return (
              <Pressable
                key={String(o.value)}
                onPress={() => onChange(o.value)}
                style={{
                  paddingHorizontal: spacing.md,
                  paddingVertical: 9,
                  borderRadius: radius.pill,
                  borderWidth: 1.5,
                  borderColor: on ? colors.primary : colors.border,
                  backgroundColor: on ? colors.primary : colors.card,
                }}
              >
                <Txt
                  variant="small"
                  weight={on ? 'bold' : 'medium'}
                  color={on ? colors.primaryForeground : colors.foreground}
                >
                  {o.label}
                </Txt>
              </Pressable>
            );
          })}
        </View>
      </ScrollView>
    </View>
  );
}

/* ---------------------------------------------------------- data rows ---- */

export function Row({
  label, value, tone, mono, last,
}: {
  label: string;
  value: React.ReactNode;
  tone?: string;
  mono?: boolean;
  last?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingVertical: 11,
        borderBottomWidth: last ? 0 : StyleSheet.hairlineWidth,
        borderBottomColor: colors.hairline,
        gap: spacing.md,
      }}
    >
      <Txt variant="small" muted style={{ flexShrink: 1 }}>{label}</Txt>
      {typeof value === 'string' || typeof value === 'number' ? (
        <Txt variant="small" weight="semibold" color={tone} mono={mono}
             style={{ flexShrink: 1, textAlign: 'right' }}>
          {value}
        </Txt>
      ) : value}
    </View>
  );
}

/** A big number tile, for the dashboard. */
export function Stat({
  label, value, tone, hint, flex = 1,
}: {
  label: string;
  value: string | number;
  tone?: string;
  hint?: string;
  flex?: number;
}) {
  const { colors } = useTheme();
  return (
    <Card style={{ flex, padding: spacing.md, minWidth: 0 }}>
      <Txt variant="caption" muted weight="semibold" numberOfLines={1}>
        {label.toUpperCase()}
      </Txt>
      <Txt variant="title" weight="bold" color={tone ?? colors.foreground}
           style={{ marginTop: 6 }} numberOfLines={1}>
        {value}
      </Txt>
      {!!hint && <Txt variant="caption" muted numberOfLines={1} style={{ marginTop: 2 }}>{hint}</Txt>}
    </Card>
  );
}

/** Horizontal share-of-total bar, for correct/wrong/blank mixes. */
export function MiniBar({
  segments, height = 10,
}: { segments: Array<{ value: number; color: string }>; height?: number }) {
  const { colors } = useTheme();
  const total = segments.reduce((s, x) => s + Math.max(0, x.value), 0);
  if (total <= 0) {
    return <View style={{ height, borderRadius: radius.pill, backgroundColor: colors.muted }} />;
  }
  return (
    <View style={{ height, borderRadius: radius.pill, overflow: 'hidden', flexDirection: 'row', backgroundColor: colors.muted }}>
      {segments.map((s, i) =>
        s.value > 0 ? (
          <View key={i} style={{ flex: s.value, backgroundColor: s.color }} />
        ) : null,
      )}
    </View>
  );
}

/* ------------------------------------------------------------- states ---- */

export function Loading({ text = 'Loading…' }: { text?: string }) {
  const { colors } = useTheme();
  return (
    <View style={styles.center}>
      <ActivityIndicator size="large" color={colors.primary} />
      <Txt variant="small" muted style={{ marginTop: spacing.md }}>{text}</Txt>
    </View>
  );
}

export function EmptyState({
  icon = '∅', title, body, action,
}: { icon?: string; title: string; body?: string; action?: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View style={styles.center}>
      <View
        style={{
          width: 64, height: 64, borderRadius: radius.pill,
          backgroundColor: colors.muted, alignItems: 'center',
          justifyContent: 'center', marginBottom: spacing.md,
        }}
      >
        <Txt variant="title">{icon}</Txt>
      </View>
      <Txt variant="heading" weight="bold" center>{title}</Txt>
      {!!body && (
        <Txt variant="small" muted center style={{ marginTop: 6, maxWidth: 300 }}>{body}</Txt>
      )}
      {!!action && <View style={{ marginTop: spacing.lg }}>{action}</View>}
    </View>
  );
}

export function ErrorState({
  message, onRetry,
}: { message: string; onRetry?: () => void }) {
  const { colors } = useTheme();
  return (
    <View style={styles.center}>
      <View
        style={{
          width: 64, height: 64, borderRadius: radius.pill,
          backgroundColor: `${colors.destructive}22`, alignItems: 'center',
          justifyContent: 'center', marginBottom: spacing.md,
        }}
      >
        <Txt variant="title" color={colors.destructive}>!</Txt>
      </View>
      <Txt variant="heading" weight="bold" center>Something went wrong</Txt>
      <Txt variant="small" muted center style={{ marginTop: 6, maxWidth: 320 }}>{message}</Txt>
      {!!onRetry && (
        <Button title="Try again" variant="outline" onPress={onRetry}
                style={{ marginTop: spacing.lg }} />
      )}
    </View>
  );
}

/** Inline banner, for a warning that should not block the screen. */
export function Notice({
  tone = 'info', title, body,
}: { tone?: 'info' | 'warning' | 'danger' | 'success'; title: string; body?: string }) {
  const { colors } = useTheme();
  const base = { info: colors.secondary, warning: colors.accent,
                 danger: colors.destructive, success: colors.success }[tone];
  return (
    <View
      style={{
        backgroundColor: `${base}18`,
        borderLeftWidth: 4,
        borderLeftColor: base,
        borderRadius: radius.sm,
        padding: spacing.md,
        marginBottom: spacing.md,
      }}
    >
      <Txt variant="small" weight="bold">{title}</Txt>
      {!!body && <Txt variant="small" muted style={{ marginTop: 3 }}>{body}</Txt>}
    </View>
  );
}

/* ------------------------------------------------------------- dialog ---- */

export function Dialog({
  visible, title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel',
  destructive, loading, onConfirm, onCancel, children,
}: {
  visible: boolean;
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  children?: React.ReactNode;
}) {
  const { colors } = useTheme();
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <Pressable
        style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: 'center', padding: spacing.xl }}
        onPress={loading ? undefined : onCancel}
      >
        <Pressable onPress={(e) => e.stopPropagation()}>
          <Card>
            <Txt variant="heading" weight="bold">{title}</Txt>
            {!!message && (
              <Txt variant="small" muted style={{ marginTop: spacing.sm }}>{message}</Txt>
            )}
            {children}
            <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.lg }}>
              <Button title={cancelLabel} variant="outline" onPress={onCancel}
                      disabled={loading} style={{ flex: 1 }} />
              <Button
                title={confirmLabel}
                variant={destructive ? 'destructive' : 'primary'}
                onPress={onConfirm}
                loading={loading}
                style={{ flex: 1 }}
              />
            </View>
          </Card>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

/* -------------------------------------------------------------- toast ---- */

type Toast = { id: number; message: string; tone: 'success' | 'error' | 'info' };
type ToastCtx = { show: (message: string, tone?: Toast['tone']) => void };

const ToastContext = React.createContext<ToastCtx>({ show: () => {} });
export const useToast = () => React.useContext(ToastContext);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);
  const next = useRef(1);

  const show = React.useCallback((message: string, tone: Toast['tone'] = 'info') => {
    const id = next.current++;
    setToasts((t) => [...t, { id, message, tone }]);
    // Errors deserve longer than a confirmation: they usually carry an action.
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)),
               tone === 'error' ? 5000 : 2800);
  }, []);

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      <View pointerEvents="none" style={styles.toastHost}>
        {toasts.map((t) => <ToastView key={t.id} toast={t} />)}
      </View>
    </ToastContext.Provider>
  );
}

function ToastView({ toast }: { toast: Toast }) {
  const { colors } = useTheme();
  const anim = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.spring(anim, { toValue: 1, useNativeDriver: true, friction: 9 }).start();
  }, [anim]);

  const base = { success: colors.success, error: colors.destructive, info: colors.primary }[toast.tone];
  return (
    <Animated.View
      style={{
        opacity: anim,
        transform: [{ translateY: anim.interpolate({ inputRange: [0, 1], outputRange: [20, 0] }) }],
        backgroundColor: colors.card,
        borderWidth: 1.5,
        borderColor: base,
        borderLeftWidth: 5,
        borderRadius: radius.md,
        padding: spacing.md,
        marginTop: spacing.sm,
        ...shadow.raised,
      }}
    >
      <Txt variant="small" weight="medium">{toast.message}</Txt>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl },
  sectionHeader: {
    flexDirection: 'row', alignItems: 'flex-end',
    justifyContent: 'space-between', marginBottom: spacing.md, gap: spacing.md,
  },
  toastHost: {
    position: 'absolute', left: spacing.lg, right: spacing.lg, bottom: 90,
  },
});

export { spacing, radius, type as typo } from '../theme';
export type { Colors };
