import { create } from 'zustand'

import type { MatchEval } from '../api/profiling'

/** Survives route changes — eval results must not vanish on tab switch. */
interface ProfilingState {
  evals: MatchEval[]
  streaming: boolean
  progress: { done: number; total: number }
  selectedCount: number
  hydrated: boolean
  addEval: (ev: MatchEval) => void
  setEvals: (evals: MatchEval[]) => void
  setStreaming: (v: boolean) => void
  setProgress: (p: { done: number; total: number }) => void
  setSelectedCount: (n: number) => void
  setHydrated: (v: boolean) => void
  reset: () => void
}

export const useProfiling = create<ProfilingState>((set) => ({
  evals: [],
  streaming: false,
  progress: { done: 0, total: 0 },
  selectedCount: 0,
  hydrated: false,
  addEval: (ev) =>
    set((state) => ({
      evals: [...state.evals.filter((e) => e.id !== ev.id || !ev.id), ev],
    })),
  setEvals: (evals) => set({ evals }),
  setStreaming: (streaming) => set({ streaming }),
  setProgress: (progress) => set({ progress }),
  setSelectedCount: (selectedCount) => set({ selectedCount }),
  setHydrated: (hydrated) => set({ hydrated }),
  reset: () =>
    set({ evals: [], streaming: false, progress: { done: 0, total: 0 }, selectedCount: 0 }),
}))
