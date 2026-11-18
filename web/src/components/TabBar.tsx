import { BookOpen, CalendarDays, ShoppingBasket, SlidersHorizontal } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { t } from "../lib/i18n";
import { defaultWeekId } from "../lib/weeks";

const TABS = [
  { to: "/plan", get label() { return t("Plan"); }, Icon: CalendarDays },
  { to: "/recipes", get label() { return t("Recipes"); }, Icon: BookOpen },
  { to: "/groceries", get label() { return t("Groceries"); }, Icon: ShoppingBasket },
  { to: "/settings", get label() { return t("Settings"); }, Icon: SlidersHorizontal },
];

export function TabBar({ badge }: { badge?: number }) {
  const { pathname } = useLocation();
  return (
    <nav aria-label={t("Main")} className="shrink-0 border-t border-line bg-card">
      <div className="mx-auto flex max-w-2xl items-stretch justify-between px-2 pb-[calc(0.5rem+env(safe-area-inset-bottom))] pt-2">
        {TABS.map(({ to, label, Icon }) => {
          const on = pathname.startsWith(to);
          return (
            <NavLink
              key={to}
              to={to === "/plan" ? `/plan/${defaultWeekId()}` : to}
              aria-current={on ? "page" : undefined}
              className={`relative flex flex-1 flex-col items-center gap-1 whitespace-nowrap py-1 text-[11px] font-semibold transition-colors duration-150 ease-out ${
                on ? "text-orange" : "text-ink-soft hover:text-ink"
              }`}
            >
              <Icon size={22} strokeWidth={on ? 2.2 : 1.8} />
              {label}
              {to === "/groceries" && badge ? (
                <span className="absolute left-1/2 top-0 ml-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-orange px-1 text-[10px] font-bold text-card">
                  {badge}
                </span>
              ) : null}
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}
