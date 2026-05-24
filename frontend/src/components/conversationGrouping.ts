/**
 * Pure helpers for the conversation sidebar: bucket conversations into
 * Today / Yesterday / Last 7 days / Older, de-duplicate near-identical titles,
 * and format a compact per-row timestamp. Kept free of JSX so the date logic
 * is easy to reason about (and test) in isolation.
 */
import type { Conversation } from "../types/chat";

export type GroupKey = "today" | "yesterday" | "week" | "older";

export interface ConversationGroup {
  key: GroupKey;
  label: string;
  items: Conversation[];
}

const GROUP_ORDER: { key: GroupKey; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "yesterday", label: "Yesterday" },
  { key: "week", label: "Last 7 days" },
  { key: "older", label: "Older" },
];

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

/** Which date bucket a conversation's `updatedAt` falls into, relative to `now`. */
export function bucketFor(updatedAt: string, now: Date = new Date()): GroupKey {
  const d = new Date(updatedAt);
  const today = startOfDay(now);
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  // "Last 7 days" spans today + the previous 6 calendar days.
  const weekAgo = new Date(today);
  weekAgo.setDate(today.getDate() - 6);

  if (d >= today) return "today";
  if (d >= yesterday) return "yesterday";
  if (d >= weekAgo) return "week";
  return "older";
}

/**
 * Bucket conversations, preserving their incoming (newest-first) order within
 * each group and dropping empty groups so only populated headers render.
 */
export function groupConversations(
  conversations: Conversation[],
  now: Date = new Date(),
): ConversationGroup[] {
  const buckets: Record<GroupKey, Conversation[]> = {
    today: [],
    yesterday: [],
    week: [],
    older: [],
  };
  for (const c of conversations) {
    buckets[bucketFor(c.updatedAt, now)].push(c);
  }
  return GROUP_ORDER.map(({ key, label }) => ({
    key,
    label,
    items: buckets[key],
  })).filter((g) => g.items.length > 0);
}

function cleanTitle(title: string): string {
  return (title || "").trim() || "Untitled conversation";
}

/**
 * Map each conversation id to a display title. Titles are the first user
 * question already; here we only disambiguate exact duplicates by appending a
 * compact date/time, so a column of identical questions stays distinguishable.
 */
export function buildDisplayTitles(
  conversations: Conversation[],
): Map<string, string> {
  const counts = new Map<string, number>();
  for (const c of conversations) {
    const base = cleanTitle(c.title);
    counts.set(base, (counts.get(base) ?? 0) + 1);
  }

  const out = new Map<string, string>();
  for (const c of conversations) {
    const base = cleanTitle(c.title);
    if ((counts.get(base) ?? 0) > 1) {
      const when = new Date(c.updatedAt).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
      out.set(c.id, `${base} · ${when}`);
    } else {
      out.set(c.id, base);
    }
  }
  return out;
}

/** Compact secondary timestamp shown per row, scaled to the group. */
export function formatRowTime(updatedAt: string, bucket: GroupKey): string {
  const d = new Date(updatedAt);
  if (bucket === "today" || bucket === "yesterday") {
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  if (bucket === "week") {
    return d.toLocaleDateString(undefined, { weekday: "short" });
  }
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
