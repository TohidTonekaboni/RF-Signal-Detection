import { create } from 'zustand'

/** Access token lives in memory only. The refresh token is an httpOnly cookie managed by the backend. */
export const useAuthStore = create((set) => ({
  accessToken: null,
  user: null, // {id, username, role, must_change_password}
  ready: false, // true once the initial /auth/refresh attempt finished
  setSession: (accessToken, user) => set({ accessToken, user, ready: true }),
  setReady: () => set({ ready: true }),
  clear: () => set({ accessToken: null, user: null, ready: true }),
}))
