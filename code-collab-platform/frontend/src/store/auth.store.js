import { create } from "zustand";

import api from "../lib/axios.js";

export const useAuthStore = create((set, get) => ({
  user: null,
  accessToken: null,
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const response = await api.post("/auth/login/", { email, password });
      set({
        user: response.data.user,
        accessToken: response.data.access_token,
        isLoading: false,
        error: null,
      });
      return response.data;
    } catch (error) {
      const detail = error.response?.data?.detail || error.message || "Login failed.";
      set({ isLoading: false, error: detail });
      throw error;
    }
  },

  logout: async () => {
    try {
      if (get().accessToken) {
        await api.post("/auth/logout/");
      }
    } catch {
      // Clear local session even if logout request fails.
    } finally {
      set({ user: null, accessToken: null, error: null });
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
  },

  refreshToken: async () => {
    const response = await api.post("/auth/refresh/");
    const accessToken = response.data.access_token;
    set({ accessToken });
    return accessToken;
  },

  fetchMe: async () => {
    set({ isLoading: true, error: null });
    try {
      const response = await api.get("/auth/me/");
      set({ user: response.data, isLoading: false });
      return response.data;
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  register: async (payload) => {
    set({ isLoading: true, error: null });
    try {
      const response = await api.post("/auth/register/", payload);
      set({ isLoading: false });
      return response.data;
    } catch (error) {
      const detail = error.response?.data?.detail || error.message || "Registration failed.";
      set({ isLoading: false, error: detail });
      throw error;
    }
  },

  clearError: () => set({ error: null }),
}));
