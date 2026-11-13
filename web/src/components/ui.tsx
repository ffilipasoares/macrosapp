import { useEffect, type ReactNode } from "react";

export function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="sheet-head">
          <h2>{title}</h2>
          <button className="icon-button" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <div className="sheet-body">{children}</div>
      </div>
    </div>
  );
}

export function Stepper({
  value,
  onChange,
  min = 1,
  max = 30,
  label,
}: {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  label: string;
}) {
  return (
    <div className="stepper" role="group" aria-label={label}>
      <button type="button" onClick={() => onChange(Math.max(min, value - 1))} disabled={value <= min} aria-label="Fewer">
        −
      </button>
      <span>{value}</span>
      <button type="button" onClick={() => onChange(Math.min(max, value + 1))} disabled={value >= max} aria-label="More">
        +
      </button>
    </div>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  return message ? (
    <p className="note note-error" role="alert">
      {message}
    </p>
  ) : null;
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return <p className="loading">{label}…</p>;
}

export function ProteinTag({ protein }: { protein: string | undefined }) {
  return protein && protein !== "other" ? <span className="tag">{protein}</span> : null;
}

export const messageOf = (error: unknown) => (error instanceof Error ? error.message : "Something went wrong. Try again.");
