# Handoff

Everything someone picking up this project needs, in one page. Last updated
18 November 2026.

## What the app is

A calm weekly meal planner for households in Portugal (later the UK). Promise:
*eat well and reach your goals, calmly, with the food you already love; saving money
comes with it.* The weekly loop: recipes go in once → every week, on the household's
chosen day, the app drafts a balanced plan → the household swaps what it doesn't
fancy → "Give me the grocery list" → shop from a shared live list → put the shopping
away in the pantry.

It is a web app added to the iPhone home screen (no App Store yet), with a Python
backend on Google Cloud. Goal for it to be worth the work: **€500 a month profit**,
about 110 households paying €6.99 a month after a 7-day trial.

## State today

- **Branches:** `main` is current and is what gets deployed. `development` exists but is
  behind. Work so far was done on `claude/loving-turing-l3b4pf` and fast-forwarded into
  `main`.
- **Backend:** 49 API routes, 283 tests passing (`cd backend && .venv/bin/pytest`).
- **Web app:** builds with `npm run build` on a machine with the packages installed.
- **Deployed:** the owner deploys by hand (see `docs/deploy.md`). Background plans need
  the one-time Cloud Tasks setup in section 3c; without it, generating a plan can hit
  a 504 through Firebase Hosting.
- **Users:** one household (the owner's), allow-listed by email. No testers yet.

## Built

| Area | What works |
|---|---|
| Recipes | Import from links (sites, TikTok), screenshots, voice, saved videos, pasted text, or typed; photos; types (main, dessert…); macros per portion; ♥ and "Not for us" |
| First-use setup | Language, people, meals cooked, plan day and hour, cooking time, diets, allergies, foods never eaten, equipment, staples, first recipe link, first plan |
| Planning | New ideas: own recipes first, then real recipe websites with a photo, then without, then written by AI (labelled, last resort). Made in the background (Cloud Tasks). Order: allergies/diets/equipment → cooking time per day → variety (nothing from last week, ≤ half from two weeks ago) → balanced week (placeholder standards) → own extra rules → taste + food at home (1 in 5 new) |
| Plan screen | Drag and drop, swap button, free choice of any recipe, "Why this", ♥ / Not for us, "I'm not cooking this" (moves to next week, food stays at home), balance line, diets-changed banner |
| Groceries | Live shared list (Firestore), offline, grouped by aisle, pack sizes ("1 bag (300 g)"), skips food at home, Siri, Put away → pantry |
| Pantry ("At home") | Add by text, voice, fridge photos; use-by estimates; meals taken out as days pass; leftovers favoured in plans |
| Taste | Learned from ♥, Not for us, swaps, choices, approvals; fades over two months; shown in Settings with Start again |
| Language | English or Portuguese (Portugal) per household: screens, recipes (translated once by AI, English names kept underneath), grocery list, notes, notifications |
| Notifications | Plan-ready push on the household's chosen day (hourly scheduler) |

## Missing and next

In order. The roadmap (claude.ai artifact, link from the owner) has the detail.

1. **Before testers:** deploy `main` with Cloud Tasks, use it for a week, fix what
   breaks. Then the **assistant** ("make Monday lighter", "one more portion", "I forgot
   the chicken"): Google ADK agent in the backend, proposes changes, user taps Apply,
   30 messages a day per household.
2. **Ten testers** in Portugal for two weeks; ask if they would pay €6.99 a month.
3. **Accounts for many:** open sign-up instead of `ALLOWED_EMAILS`, partner invites
   (today a couple shares one Google account), delete account (GDPR).
4. **Paying:** 7-day trial and Stripe on the web; privacy policy and terms.
5. **Ready for many:** AI usage limits, App Check, versioned API, staging project,
   monitoring, shared catalogue of checked web recipes.
6. **iPhone app** (Capacitor, TestFlight, App Store subscriptions), then launch.
7. **When the nutritionist answers:** replace `backend/app/standards/default.json` with her
   balanced-week rules. Ready-made weeks with her come much later.

Not built, on purpose for now: weekly tips (dropped), weekday taste patterns (needs
months of data), per-person taste (needs partner accounts), selling to nutritionists
(ruled out).

## Decisions already made

- Plans are chosen by **code, not AI**; AI only reads, writes and translates recipes,
  checks diets/allergies once per recipe, and finds web recipes.
- **Rules order** as in "Planning" above; choosing by hand is always free.
- **Variety is fixed for everyone** (no settings): nothing from last week, ≥ 50% new
  versus two weeks before.
- **Allergies** are checked twice (word lists + AI verdict); never planned; a warning if
  chosen by hand; the app tells people to check labels.
- **One taste and one language per household.**
- **English ingredient names underneath** every recipe and pantry item; Portuguese is a
  display label. Matching (allergies, pantry, packs, diets) never depends on language.
- **Standards and pack sizes are data files**, not code.
- **Web app first**; payments on the web (Stripe) before the App Store.
- **Google Cloud + Python** (FastAPI, Firestore, Vertex AI Gemini, Cloud Run, Cloud
  Tasks, Cloud Scheduler).

## Running it

Locally, against Firebase emulators with a stand-in AI (no Google account needed):
see "Run it locally" in `README.md`. Notes:

- The stand-in AI writes sample dinners so an empty library still gets a week, and
  "translates" by adding `[pt]` — real Portuguese only comes from Gemini.
- `web/.env.development` forces local runs to the local backend even if `.env.local`
  points `VITE_API_URL` at Cloud Run.
- A fresh development sign-in is a new household, so the first-use setup shows.

Deploying: `docs/deploy.md`. When redeploying the backend, leave out `--set-env-vars`
(it replaces every variable); use `--update-env-vars` for changes.

## Gotchas

- **npm and Airlock.** `web/package-lock.json` points at the owner's corporate Airlock
  proxy, so `npm ci` fails on GitHub Actions (the CI web job is red for that reason
  alone) and in cloud agent sessions. Rewriting the lockfile or CI to bypass Airlock was
  blocked as a policy question; the owner decides. Agents here cannot install the web
  packages: type-check with a global `tsc` and ignore "cannot find module" errors.
- **API types are hand-edited.** `web/src/api-types.ts` normally comes from
  `npm run gen:types`; recent fields were added by hand. Regenerate when possible.
- **Screen text goes through `t()`** (`web/src/lib/i18n.ts`). New English text needs a
  Portuguese entry in `web/src/lib/i18n-pt.ts`; missing entries fall back to English.
  Backend text for people goes through `backend/app/i18n.py`.
- **Firestore is backend-only** except the grocery list (`firestore.rules`).
- **Gemini model and region:** `GEMINI_MODEL` (default `gemini-3.5-flash`),
  `GEMINI_LOCATION` (default `global`).
- **Commits:** small, with a plain-English message; push to the working branch; merge
  to `main` only when the owner asks.

## Where to look

| For | Read |
|---|---|
| Features and screens | `README.md` |
| Diagrams, data, where code lives | `docs/architecture.md` |
| Deploying | `docs/deploy.md` |
| Siri and share sheet | `docs/shortcuts.md` |
| Planner rules | `backend/app/core/planner.py`, `backend/app/services.py` (`generate_plan`) |
| Balanced week | `backend/app/standards/default.json`, `backend/app/core/balance.py` |
