"use client";

/**
 * Auth context — the single source of truth for "who is logged in".
 *
 * On mount it validates the stored token by calling /auth/me (so a stale
 * token logs the user out cleanly). Login/signup store the token pair and
 * fetch the user; logout revokes the refresh token server-side too.
 */

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { ApiClientError, tokenStore } from "./api";
import { authApi } from "./endpoints";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (body: {
    email: string;
    password: string;
    full_name: string;
    organization_name: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  // Validate any persisted token once on load.
  useEffect(() => {
    (async () => {
      if (!tokenStore.access) {
        setLoading(false);
        return;
      }
      try {
        setUser(await authApi.me());
      } catch {
        tokenStore.clear();
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const pair = await authApi.login(email, password);
    tokenStore.set(pair);
    setUser(await authApi.me());
    router.push("/dashboard");
  }, [router]);

  const signup = useCallback(
    async (body: {
      email: string;
      password: string;
      full_name: string;
      organization_name: string;
    }) => {
      await authApi.signup(body);
      // Signup returns the user, not tokens — log in to get a session.
      await login(body.email, body.password);
    },
    [login]
  );

  const logout = useCallback(async () => {
    const refresh = tokenStore.refresh;
    if (refresh) {
      try {
        await authApi.logout(refresh);
      } catch (e) {
        if (!(e instanceof ApiClientError)) throw e; // ignore auth errors on logout
      }
    }
    tokenStore.clear();
    setUser(null);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
