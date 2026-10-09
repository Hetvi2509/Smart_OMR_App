import { NavigationContainer, DefaultTheme, DarkTheme } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import React from 'react';

import AnswerKeyScreen from '../screens/AnswerKeyScreen';
import DashboardScreen from '../screens/DashboardScreen';
import EditTestScreen from '../screens/EditTestScreen';
import HistoryScreen from '../screens/HistoryScreen';
import LoginScreen from '../screens/LoginScreen';
import ReportsScreen from '../screens/ReportsScreen';
import ResultScreen from '../screens/ResultScreen';
import ScanScreen from '../screens/ScanScreen';
import SettingsScreen from '../screens/SettingsScreen';
import SignUpScreen from '../screens/SignUpScreen';
import TestDetailScreen from '../screens/TestDetailScreen';
import TestsScreen from '../screens/TestsScreen';
import { useAuth } from '../store/auth';
import { fonts } from '../theme';
import { useTheme } from '../theme/ThemeProvider';
import { Loading } from '../ui';
import FloatingTabBar from './FloatingTabBar';

const Stack = createNativeStackNavigator();
const Tabs = createBottomTabNavigator();

function MainTabs() {
  return (
    <Tabs.Navigator
      // The floating pill bar replaces the default flat tab bar entirely;
      // tabBarStyle/tabBarIcon below no longer apply once tabBar is set.
      tabBar={(props) => <FloatingTabBar {...props} />}
      screenOptions={{ headerShown: false }}
    >
      <Tabs.Screen name="Dashboard" component={DashboardScreen} />
      <Tabs.Screen name="Tests" component={TestsScreen} />
      <Tabs.Screen name="Scan" component={ScanScreen} options={{ tabBarLabel: 'Scan' }} />
      <Tabs.Screen name="History" component={HistoryScreen} />
      <Tabs.Screen name="Reports" component={ReportsScreen} />
      <Tabs.Screen name="Profile" component={SettingsScreen} />
    </Tabs.Navigator>
  );
}

export default function RootNavigator() {
  const { colors, dark } = useTheme();
  const { user, ready } = useAuth();

  const navTheme = {
    ...(dark ? DarkTheme : DefaultTheme),
    colors: {
      ...(dark ? DarkTheme : DefaultTheme).colors,
      primary: colors.primary,
      background: colors.background,
      card: colors.card,
      text: colors.foreground,
      border: colors.border,
    },
  };

  if (!ready) return <Loading text="Starting up…" />;

  return (
    <NavigationContainer theme={navTheme}>
      <Stack.Navigator
        screenOptions={{
          headerStyle: { backgroundColor: colors.card },
          headerTintColor: colors.foreground,
          headerTitleStyle: { fontFamily: fonts.semibold },
          contentStyle: { backgroundColor: colors.background },
        }}
      >
        {!user ? (
          <>
            <Stack.Screen name="Login" component={LoginScreen}
                          options={{ headerShown: false }} />
            <Stack.Screen name="SignUp" component={SignUpScreen}
                          options={{ title: 'Create account', headerShown: false }} />
          </>
        ) : (
          <>
            <Stack.Screen name="Main" component={MainTabs}
                          options={{ headerShown: false }} />
            <Stack.Screen name="EditTest" component={EditTestScreen}
                          options={{ headerShown: false }} />
            <Stack.Screen name="TestDetail" component={TestDetailScreen}
                          options={{ headerShown: false }} />
            <Stack.Screen name="AnswerKey" component={AnswerKeyScreen}
                          options={{ headerShown: false }} />
            <Stack.Screen name="Result" component={ResultScreen}
                          options={{ headerShown: false }} />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}
