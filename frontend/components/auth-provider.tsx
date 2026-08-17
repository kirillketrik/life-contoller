"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext } from "react";

import { ApiError, auth } from "@/lib/api";
import type { CurrentUser, LoginInput } from "@/lib/types";

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  login: (input: LoginInput) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);
const ME_QUERY_KEY = ["auth", "me"] as const;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();

  const meQuery = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: async () => {
      try {
        return await auth.me();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
  });

  const loginMutation = useMutation({
    mutationFn: auth.login,
    onSuccess: (user) => queryClient.setQueryData(ME_QUERY_KEY, user),
  });

  const logoutMutation = useMutation({
    mutationFn: auth.logout,
    onSuccess: () => queryClient.setQueryData(ME_QUERY_KEY, null),
  });

  return (
    <AuthContext.Provider
      value={{
        user: meQuery.data ?? null,
        loading: meQuery.isLoading,
        login: async (input) => {
          await loginMutation.mutateAsync(input);
        },
        logout: async () => {
          await logoutMutation.mutateAsync();
        },
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
