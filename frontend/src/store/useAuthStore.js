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


