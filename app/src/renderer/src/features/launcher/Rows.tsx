/**
 * Feature: launcher. The rows of the results list. Every row is ROW_H tall and absolutely placed in
 * its slot, so a skeleton and the result that replaces it crossfade in place (no reflow, no jump).
 */
import { AnimatePresence, motion } from "motion/react";
import type { ReactNode } from "react";
import {
  CircleAlert,
  CornerDownLeft,
  FileCode2,
  FileText,
  FolderGit2,
  Newspaper,
  SearchX,
  Sparkles,
} from "lucide-react";
import { Thumb } from "../../core/ui/atoms";
import { clock, color, spring } from "../../core/theme";
import type { SearchResult } from "./store";
import { thumbnailFor, type YouTubeLink } from "./youtube";
import { kindTone, rgba, tint } from "./tint";

export const ROW_H = 64;

const enter = { opacity: 0, y: 8 };
const shown = { opacity: 1, y: 0 };
const gone = { opacity: 0, transition: { duration: 0.12 } };

type Slot = { slot: number; delay?: number };

function RowShell({
  slot,
  delay = 0,
  selected = false,
  children,
  onHover,
  onPick,
}: Slot & {
  selected?: boolean;
  children: ReactNode;
  onHover?: () => void;
  onPick?: () => void;
}): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      className="absolute inset-x-0 flex cursor-pointer items-center gap-[14px] pl-[10px] pr-[12px] text-left"
      style={{ top: slot * ROW_H, height: ROW_H }}
      initial={enter}
      animate={shown}
      exit={gone}
      transition={{ ...spring, delay }}
      // Keep the caret in the input: rows are pointer targets, not focus stops.
      onMouseDown={(e) => e.preventDefault()}
      onMouseMove={onHover}
      onClick={onPick}
    >
      {children}
      {/* ↵ appears on the chosen row: Enter builds this one. */}
      <span className="grid w-[26px] shrink-0 place-items-center">
        <AnimatePresence initial={false}>
          {selected && (
            <motion.span
              className="grid h-[24px] w-[26px] place-items-center rounded-[8px] text-white/80"
              style={{ background: "rgba(255,255,255,.1)" }}
              initial={{ opacity: 0, scale: 0.7 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.7, transition: { duration: 0.1 } }}
              transition={spring}
            >
              <CornerDownLeft size={12} strokeWidth={2.2} />
            </motion.span>
          )}
        </AnimatePresence>
      </span>
    </motion.button>
  );
}

/** A 64×42 tile: the video's thumbnail, or a glyph tinted by the source kind. */
function Tile({
  r,
}: {
  r: Pick<SearchResult, "kind" | "thumbnail">;
}): ReactNode {
  if (r.kind === "video")
    return (
      <span className="relative shrink-0">
        <Thumb w={64} h={42} src={r.thumbnail} />
        <span
          className="pointer-events-none absolute inset-0 rounded-[6px]"
          style={{ boxShadow: "inset 0 0 0 1px rgba(255,255,255,.1)" }}
        />
      </span>
    );
  const I =
    r.kind === "repo"
      ? FolderGit2
      : r.kind === "notebook"
        ? FileCode2
        : r.kind === "paper"
          ? FileText
          : Newspaper;
  const tone = kindTone[r.kind] ?? color.gray;
  return (
    <span
      className="grid h-[42px] w-[64px] shrink-0 place-items-center rounded-[10px]"
      style={{
        background: `linear-gradient(160deg, ${rgba(tone, 0.22)}, ${rgba(tone, 0.06)})`,
        color: tone,
        boxShadow: `inset 0 0 0 1px ${rgba(tone, 0.22)}`,
      }}
    >
      <I size={18} strokeWidth={1.7} />
    </span>
  );
}

function Text({ title, meta }: { title: string; meta: string }): ReactNode {
  return (
    <span className="min-w-0 flex-1">
      <span className="block truncate text-[15px] font-semibold leading-[20px] tracking-[-0.005em] text-white">
        {title}
      </span>
      <span
        className="mt-[1px] block truncate text-[12.5px] leading-[18px]"
        style={{ color: color.faint }}
      >
        {meta}
      </span>
    </span>
  );
}

/** Why this result: the best one gets a lit badge, the rest a quiet outline. */
function Reason({ text, best }: { text: string; best: boolean }): ReactNode {
  if (!text) return null;
  return best ? (
    <span
      className="inline-flex h-[24px] shrink-0 items-center gap-[5px] rounded-full pl-[8px] pr-[10px] text-[12px] font-semibold"
      style={{
        background: tint.accentBadge,
        color: tint.accentText,
        boxShadow: `inset 0 0 0 1px ${rgba(color.accent, 0.3)}`,
      }}
    >
      <Sparkles size={11} strokeWidth={2} />
      {text}
    </span>
  ) : (
    <span
      className="inline-flex h-[24px] shrink-0 items-center rounded-full border px-[10px] text-[12px] font-medium"
      style={{ color: color.label, borderColor: tint.chipBorder }}
    >
      {text}
    </span>
  );
}

export function ResultRow({
  r,
  best,
  selected,
  ...rest
}: Slot & {
  r: SearchResult;
  best: boolean;
  selected: boolean;
  onHover: () => void;
  onPick: () => void;
}): ReactNode {
  return (
    <RowShell {...rest} selected={selected}>
      <Tile r={r} />
      <Text title={r.title} meta={r.meta} />
      <Reason text={r.reason} best={best} />
    </RowShell>
  );
}

/** A pasted YouTube link: no search, one row, Enter builds straight from it. */
export function LinkRow({
  link,
  onPick,
}: {
  link: YouTubeLink;
  onPick: () => void;
}): ReactNode {
  return (
    <RowShell slot={0} selected onPick={onPick}>
      <Tile r={{ kind: "video", thumbnail: thumbnailFor(link.videoId) }} />
      <Text
        title="YouTube video"
        meta={`youtu.be/${link.videoId}${link.start ? ` · from ${clock(link.start)}` : ""}`}
      />
      <Reason text="Build from link" best />
    </RowShell>
  );
}

/** Placeholder while results stream in: a light sweeping across, staggered per slot. */
export function SkeletonRow({ slot }: { slot: number }): ReactNode {
  const bar = { background: tint.skeleton, backgroundSize: "200% 100%" };
  const sweep = { backgroundPosition: ["100% 0%", "-100% 0%"] };
  const loop = {
    duration: 1.5,
    repeat: Infinity,
    ease: "linear" as const,
    delay: slot * 0.15,
  };
  return (
    <motion.div
      className="absolute inset-x-0 flex items-center gap-[14px] pl-[10px] pr-[12px]"
      style={{ top: slot * ROW_H, height: ROW_H }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={gone}
      transition={{ duration: 0.2 }}
    >
      <motion.span
        className="h-[42px] w-[64px] shrink-0 rounded-[10px]"
        style={bar}
        animate={sweep}
        transition={loop}
      />
      <span className="flex flex-1 flex-col gap-[8px]">
        <motion.span
          className="h-[11px] rounded-full"
          style={{ ...bar, width: `${56 - slot * 9}%` }}
          animate={sweep}
          transition={loop}
        />
        <motion.span
          className="h-[9px] rounded-full"
          style={{ ...bar, width: `${32 + slot * 6}%` }}
          animate={sweep}
          transition={loop}
        />
      </span>
    </motion.div>
  );
}

/** Empty / error: one quiet row with an icon, a title and a detail line. */
export function MessageRow({
  tone,
  title,
  detail,
}: {
  tone: "empty" | "error";
  title: string;
  detail: string;
}): ReactNode {
  const I = tone === "error" ? CircleAlert : SearchX;
  const c = tone === "error" ? color.amber : color.gray;
  return (
    <motion.div
      className="absolute inset-x-0 flex items-center gap-[14px] pl-[10px] pr-[12px]"
      style={{ top: 0, height: ROW_H }}
      initial={enter}
      animate={shown}
      exit={gone}
      transition={spring}
    >
      <span
        className="grid h-[42px] w-[64px] shrink-0 place-items-center rounded-[10px]"
        style={{
          background: rgba(c, 0.12),
          color: c,
          boxShadow: `inset 0 0 0 1px ${rgba(c, 0.2)}`,
        }}
      >
        <I size={18} strokeWidth={1.7} />
      </span>
      <Text title={title} meta={detail} />
    </motion.div>
  );
}
