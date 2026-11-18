import { Heart, ThumbsDown } from "lucide-react";
import { t } from "../lib/i18n";

/** ♥ (more of this) and "Not for us" (never suggest it). Both can be taken back. */
export function Feedback({
  liked,
  notForUs,
  disabled,
  onLike,
  onNotForUs,
}: {
  liked: boolean;
  notForUs: boolean;
  disabled?: boolean;
  onLike: () => void;
  onNotForUs: () => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <button
        type="button"
        onClick={onLike}
        disabled={disabled}
        aria-pressed={liked}
        className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold transition-colors duration-150 ease-out disabled:opacity-40 ${
          liked ? "bg-pink-soft text-ink" : "bg-card text-ink ring-1 ring-line hover:ring-ink-soft"
        }`}
      >
        <Heart size={16} className={liked ? "fill-pink text-pink" : ""} /> {liked ? t("Loved") : t("Love it")}
      </button>
      <button
        type="button"
        onClick={onNotForUs}
        disabled={disabled}
        aria-pressed={notForUs}
        className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold transition-colors duration-150 ease-out disabled:opacity-40 ${
          notForUs ? "bg-ink text-paper" : "bg-card text-ink ring-1 ring-line hover:ring-ink-soft"
        }`}
      >
        <ThumbsDown size={16} /> {t("Not for us")}
      </button>
    </div>
  );
}
