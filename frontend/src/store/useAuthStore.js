import { create } from "zustand";
import { http } from "../api/client";

export const useAuthStore = create((set) => ({
  user: null,
  loading: true,
  
  checkAuth: async () => {
    try {
      const { data } = await http.get("/auth/me");
      set({ user: data, loading: false });
    } catch (error) {
      set({ user: null, loading: false });
    }
  },

  login: async (username, password) => {
    const { data } = await http.post("/auth/login", { username, password });
    set({ user: data, loading: false });
    return data;
  },

  googleLogin: async (credential, professionalDetails = {}) => {
    const { data } = await http.post("/auth/google/login", { credential, ...professionalDetails });
    set({ user: data, loading: false });
    return data;
  },

  adminLogin: async (username, password) => {
    const { data } = await http.post("/auth/admin-login", { username, password });
    set({ user: data, loading: false });
    return data;
  },

  logout: async () => {
    try {
      await http.post("/auth/logout");
    } catch (error) {
      console.error("Logout failed", error);
    } finally {
      set({ user: null });
      window.location.href = "/login";
    }
  }
}));


