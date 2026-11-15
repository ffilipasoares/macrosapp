import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, Minus, Plus, X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { ease, proteinStyle } from "../lib/style";

/** Bottom sheet: slides up over the screen. */
export function Sheet({ title, subtitle, onClose, children }: { title: string; subtitle?: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <AnimatePresence>
      <motion.div
        key="scrim"
        className="fixed inset-0 z-30 bg-ink/30"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.2, ease }}
        onClick={onClose}
      />
      <motion.section
        key="sheet"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="fixed inset-x-0 bottom-0 z-40 mx-auto flex max-h-[88dvh] max-w-2xl flex-col rounded-t-3xl bg-paper"
        initial={{ y: "100%" }}
        animate={{ y: 0 }}
        transition={{ duration: 0.28, ease }}
      >
        <div className="flex items-start justify-between gap-3 px-5 pt-5">
          <div className="min-w-0">
            <h2 className="text-xl font-bold">{title}</h2>
            {subtitle ? <p className="mt-1 text-sm text-ink-soft">{subtitle}</p> : null}
          </div>
          <button onClick={onClose} aria-label="Close" className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-card text-ink-soft">
            <X size={18} />
          </button>
        </div>
        <div className="flex flex-col gap-3 overflow-y-auto px-5 pb-[calc(2rem+env(safe-area-inset-bottom))] pt-4">{children}</div>
      </motion.section>
    </AnimatePresence>
  );
}

/** Full-screen page that sits over the tab bar, with a back button. */
export function Overlay({ children }: { children: ReactNode }) {
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);
  return (
    <motion.div
      className="fixed inset-0 z-30 overflow-y-auto bg-paper"
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.22, ease }}
    >
      {children}
    </motion.div>
  );
}

export function BackButton({ onClick, floating = false }: { onClick: () => void; floating?: boolean }) {
  return (
    <button
      onClick={onClick}
      aria-label="Back"
      className={
        floating
          ? "absolute left-4 top-[calc(1rem+env(safe-area-inset-top))] grid h-10 w-10 place-items-center rounded-full bg-card/90 text-ink"
          : "-ml-2 grid h-10 w-10 shrink-0 place-items-center rounded-full text-ink transition-colors duration-150 ease-out hover:bg-card"
      }
    >
      <ArrowLeft size={20} />
    </button>
  );
}

export function Stepper({ value, onChange, min = 1, max = 30, label }: { value: number; onChange: (value: number) => void; min?: number; max?: number; label: string }) {
  const step = (delta: number, text: string, icon: ReactNode, disabled: boolean) => (
    <motion.button
      type="button"
      whileTap={{ scale: 0.92 }}
      transition={{ duration: 0.1, ease }}
      onClick={() => onChange(Math.min(max, Math.max(min, value + delta)))}
      disabled={disabled}
      aria-label={text}
      className="grid h-10 w-10 place-items-center rounded-full bg-card text-ink ring-1 ring-line disabled:opacity-40"
    >
      {icon}
    </motion.button>
  );
  return (
    <div className="flex items-center gap-2" role="group" aria-label={label}>
      {step(-1, "Fewer", <Minus size={18} />, value <= min)}
      <span className="w-8 text-center text-2xl font-bold tabular-nums">{value}</span>
      {step(1, "More", <Plus size={18} />, value >= max)}
    </div>
  );
}

/** A recipe's picture: its photo if it has one, otherwise its first letter on the protein's tint. */
export function Thumb({
  title,
  protein,
  image,
  size = "sm",
}: {
  title: string;
  protein?: string | null;
  image?: string | null;
  size?: "sm" | "tile" | "hero";
}) {
  const p = proteinStyle(protein);
  const letter = (title.trim()[0] ?? "?").toUpperCase();
  const box =
    size === "hero"
      ? "mx-auto aspect-[4/3] max-h-[320px] w-full max-w-2xl text-7xl"
      : size === "tile"
        ? "aspect-square w-full rounded-2xl text-4xl"
        : "h-12 w-12 shrink-0 rounded-xl text-lg";
  return (
    <span className={`relative grid place-items-center overflow-hidden font-bold text-ink/60 ${p.soft} ${box}`}>
      {letter}
      {image ? (
        <img
          src={image}
          alt=""
          loading="lazy"
          className="absolute inset-0 h-full w-full object-cover"
          onError={(e) => (e.currentTarget.style.display = "none")}
        />
      ) : null}
    </span>
  );
}

export function ProteinDot({ protein, withLabel = true }: { protein?: string | null; withLabel?: boolean }) {
  const p = proteinStyle(protein);
  return (
    <span className="flex items-center gap-1.5">
      <span className={`h-2 w-2 rounded-full ${p.bg}`} aria-hidden="true" />
      {withLabel ? p.label : null}
    </span>
  );
}

export function NewIdea() {
  return <span className="rounded-full bg-periwinkle-soft px-2 py-0.5 text-xs font-semibold text-ink">New idea</span>;
}

export function ErrorNote({ message }: { message: string | null }) {
  return message ? (
    <p className="rounded-2xl bg-orange-soft px-4 py-3 text-sm font-medium text-orange" role="alert">
      {message}
    </p>
  ) : null;
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-ink-soft" role="status">
      <Dots bouncing />
      <span className="text-sm">{label}…</span>
    </div>
  );
}

export function Dots({ bouncing = false }: { bouncing?: boolean }) {
  return (
    <div className="flex gap-2" aria-hidden="true">
      {["bg-blue", "bg-orange", "bg-mustard", "bg-green", "bg-pink"].map((color, i) => (
        <motion.span
          key={color}
          className={`h-3 w-3 rounded-full ${color}`}
          animate={bouncing ? { y: [0, -6, 0] } : { y: 0 }}
          transition={bouncing ? { duration: 0.6, repeat: Infinity, delay: i * 0.08, ease: "easeInOut" } : undefined}
        />
      ))}
    </div>
  );
}

export const primaryButton =
  "flex items-center justify-center gap-2 whitespace-nowrap rounded-full bg-orange px-6 py-3 font-bold text-card transition-opacity duration-150 ease-out disabled:opacity-40";
export const darkButton = "flex items-center justify-center gap-2 whitespace-nowrap rounded-full bg-ink px-5 py-3 font-semibold text-paper disabled:opacity-40";
export const quietButton =
  "flex items-center justify-center gap-2 whitespace-nowrap rounded-full border border-line bg-card px-5 py-3 font-semibold text-ink disabled:opacity-40";
export const listButton = "-mx-2 flex w-[calc(100%+16px)] items-center gap-3 rounded-2xl p-2 text-left transition-colors duration-150 ease-out hover:bg-card disabled:opacity-50";

export const messageOf = (error: unknown) => (error instanceof Error ? error.message : "Something went wrong. Try again.");

