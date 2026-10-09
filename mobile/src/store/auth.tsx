import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { ApiError, loadSession, setToken } from '../api/client';
import { endpoints } from '../api/endpoints';
import { User } from '../api/types';
import { clearApiCache } from '../hooks/useApi';

type AuthCtx = {
  user: User | null;
  ready: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (body: {
    email: string; password: string; full_name: string;
    institution_name?: string | null;
  }) => Promise<void>;
  signOut: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // Restore the saved token on launch and confirm it still works, so a
    // revoked or expired session does not leave the app showing a dashboard
    // it cannot load.
    (async () => {
      try {
        const { token } = await loadSession();
        if (token) {
          try {
            setUser((await endpoints.me()).user);
          } catch (err) {
            // 401 means the token is dead; anything else (server down) should
            // not silently sign the user out of a valid session.
            if (err instanceof ApiError && err.status === 401) await setToken(null);
          }
        }
      } finally {
        setReady(true);
      }
    })();
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const res = await endpoints.login({ email: email.trim(), password });
    await setToken(res.token);
    // Whatever is cached belongs to whoever was signed in before.
    clearApiCache();
    setUser(res.user);
  }, []);

  const signUp = useCallback(async (body: Parameters<AuthCtx['signUp']>[0]) => {
    const res = await endpoints.signup({ ...body, email: body.email.trim() });
    await setToken(res.token);
    clearApiCache();
    setUser(res.user);
  }, []);

  const signOut = useCallback(async () => {
    await setToken(null);
    // Cached responses belong to the account that fetched them; leaving them
    // in memory would show one user's results to the next person who signs in.
    clearApiCache();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, ready, signIn, signUp, signOut }),
    [user, ready, signIn, signUp, signOut],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
