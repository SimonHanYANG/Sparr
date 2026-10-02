import { create } from 'zustand'

import { apiFetch, clearTokens, getAccessToken, setTokens } from '../api/client'

export interface User {
  id: number
  username: string
  email: string
  nickname: string
}

interface AuthState {
  user: User | null
  loggedIn: boolean
  login: (username: string, password: string) => Promise<void>
  register: (payload: {
    username: string
    password: string
    email?: string
    nickname?: string
  }) => Promise<void>
  fetchMe: () => Promise<void>
  logout: () => void
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  loggedIn: Boolean(getAccessToken()),

  login: async (username, password) => {
    const data = await apiFetch<{ access: string; refresh: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    setTokens(data.access, data.refresh)
    set({ loggedIn: true })
    const user = await apiFetch<User>('/api/auth/me')
    set({ user })
  },

  register: async (payload) => {
    await apiFetch('/api/auth/register', { method: 'POST', body: JSON.stringify(payload) })
  },

  fetchMe: async () => {
    if (!getAccessToken()) return
    try {
      const user = await apiFetch<User>('/api/auth/me')
      set({ user, loggedIn: true })
    } catch {
      clearTokens()
      set({ user: null, loggedIn: false })
    }
  },

  logout: () => {
    clearTokens()
    set({ user: null, loggedIn: false })
  },
}))
