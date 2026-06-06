import { useEffect } from "react";

import { useAuthStore } from "../store/auth.store.js";

export function useAuth() {
  const user = useAuthStore((state) => state.user);
  const accessToken = useAuthStore((state) => state.accessToken);
  const isLoading = useAuthStore((state) => state.isLoading);
  const error = useAuthStore((state) => state.error);
  const login = useAuthStore((state) => state.login);
  const logout = useAuthStore((state) => state.logout);
  const fetchMe = useAuthStore((state) => state.fetchMe);
  const register = useAuthStore((state) => state.register);
  const clearError = useAuthStore((state) => state.clearError);

  useEffect(() => {
    if (!user && accessToken) {
      fetchMe().catch(() => {
        useAuthStore.setState({ accessToken: null });
      });
    }
  }, [user, accessToken, fetchMe]);

  return {
    user,
    accessToken,
    isAuthenticated: Boolean(user),
    isLoading,
    error,
    login,
    logout,
    register,
    clearError,
  };
}
