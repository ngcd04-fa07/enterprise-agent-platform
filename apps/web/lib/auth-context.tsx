"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { api, ApiError } from "@/lib/api";

export type MembershipRole = "admin" | "underwriter" | "reviewer" | "viewer";

export interface Membership {
  organisation_id: string;
  role: MembershipRole;
}

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
}

interface MeResponse {
  user: AuthUser;
  memberships: Membership[];
  active_organisation_id: string | null;
  csrf_token: string;
}

interface AuthState {
  user: AuthUser | null;
  memberships: Membership[];
  activeOrganisationId: string | null;
  csrfToken: string | null;
  loading: boolean;
}

interface AuthContextValue extends AuthState {
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const initialState: AuthState = {
  user: null,
  memberships: [],
  activeOrganisationId: null,
  csrfToken: null,
  loading: true,
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(initialState);

  const refresh = useCallback(async () => {
    try {
      const me = await api.get<MeResponse>("/auth/me");
      setState({
        user: me.user,
        memberships: me.memberships,
        activeOrganisationId: me.active_organisation_id,
        csrfToken: me.csrf_token,
        loading: false,
      });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setState({ ...initialState, loading: false });
        return;
      }
      throw error;
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    if (state.csrfToken) {
      await api.post("/auth/logout", undefined, state.csrfToken);
    }
    setState({ ...initialState, loading: false });
  }, [state.csrfToken]);

  return (
    <AuthContext.Provider value={{ ...state, refresh, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
