import {
  PlusJakartaSans_400Regular,
  PlusJakartaSans_500Medium,
  PlusJakartaSans_600SemiBold,
  PlusJakartaSans_700Bold,
  useFonts,
} from '@expo-google-fonts/plus-jakarta-sans';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import RootNavigator from './src/navigation/RootNavigator';
import { AuthProvider } from './src/store/auth';
import { palette } from './src/theme';
import { ThemeProvider, useTheme } from './src/theme/ThemeProvider';
import { ToastProvider } from './src/ui';

export default function App() {
  // Plus Jakarta Sans is the theme's own family. Rendering before it loads
  // would show the whole app in the platform default and then reflow, so the
  // first frame waits on it.
  const [fontsLoaded, fontError] = useFonts({
    PlusJakartaSans_400Regular,
    PlusJakartaSans_500Medium,
    PlusJakartaSans_600SemiBold,
    PlusJakartaSans_700Bold,
  });

  // A font that fails to load must not block the app; it falls back silently.
  if (!fontsLoaded && !fontError) {
    return <View style={{ flex: 1, backgroundColor: palette.light.background }} />;
  }

  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <ToastProvider>
          <AuthProvider>
            <Chrome />
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}

/** Inside ThemeProvider so the status bar can follow the chosen theme. */
function Chrome() {
  const { dark } = useTheme();
  return (
    <>
      <StatusBar style={dark ? 'light' : 'dark'} />
      <RootNavigator />
    </>
  );
}
