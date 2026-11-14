/** Feature: launcher. Search state: results stream in from the engine; errors land here while a search is live. */
import { create } from "zustand";
import type { Payload } from "../../../../common/wire";
import { onMessage, onUi } from "../../core/bus";

export type SearchResult = Payload<"search.result">;

type SearchState = {
  /** The query the results belong to (the input may have moved on). */
  query: string;
  results: SearchResult[];
  /** A learn is in flight: rows may still stream in. */
  pending: boolean;
  done: boolean;
  total?: number;
  /** Engine `error` that arrived while a search was in flight or the launcher was open. */
  error?: string;
  /** The launcher panel is showing (set by the component). */
  open: boolean;
};

const blank = {
  query: "",
  results: [],
  pending: false,
  done: false,
  total: undefined,
  error: undefined,
} satisfies Partial<SearchState>;

export const useSearch = create<SearchState>(() => ({ ...blank, open: false }));
const set = useSearch.setState;
const get = useSearch.getState;

export const startSearch = (query: string): void =>
  set({ ...blank, query, pending: true });
export const setLauncherOpen = (open: boolean): void => {
  if (get().open !== open) set({ open });
};

onUi("reset", () => set({ ...blank }));

onMessage("search.result", (p) =>
  set((s) => ({
    results: s.results.filter((r) => r.id !== p.id).concat(p),
    pending: !s.done,
    error: undefined,
  })),
);
onMessage("search.done", (p) =>
  set({ done: true, pending: false, total: p.total }),
);
onMessage("error", (p) => {
  const s = get();
  if (s.pending || s.open) set({ error: p.message, pending: false });
});
