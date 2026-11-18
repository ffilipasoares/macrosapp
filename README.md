# Meal Planner

A personal app for one weekly routine: decide what to cook, then get the grocery
list for it. Recipes go in once; every week, on the day you choose, the app drafts next week's plan
from them, following your rules; you swap what you don't fancy and tap
**Give me the grocery list**.

It is a web app you add to the iPhone home screen, with a Python backend on
Google Cloud.

## What it does

| You want to | The app |
|---|---|
| See new ideas before cooking them | New recipes come from real recipe websites only (never code sites, forums or social media), those with a photo first. Recipes written by AI are the last resort, only for meals still empty, and are labelled "Written by AI" |
| Never wait on a frozen screen | Plans are made in the background (Cloud Tasks): the app shows "Planning your week…" and the plan appears when ready, even after leaving the screen |
| Stop planning from a blank page | Drafts next week's meals on the day and hour you choose (Friday 17:00 by default) and notifies you |
| Use the app in Portuguese or English | One language per household, chosen in the first-use setup (it starts from the phone's language) and in Settings. Screens, recipes, the grocery list, plan notes and notifications follow it. Recipes are translated once by AI; ingredient names stay English underneath, so allergies, the pantry and packs keep matching |
| Start without an empty app | A short first-use setup asks who eats, which meals you cook, when the plan should be ready, diets, allergies, foods you never eat, kitchen equipment and staples, then makes the first plan |
| Stay safe with allergies | Recipes with any of the 14 EU allergens you choose, or your own, are never planned or swapped in; checked by ingredient names and once per recipe by AI. Choosing one by hand shows a warning |
| Learn your taste | ♥ and "Not for us" on any recipe or planned meal, plus what you do: swaps count against, meals you choose for, approved plans a little. Recent actions count most. Plans, the swap button, the order of suggestions and web searches use it, always after your rules; one meal in five is something new. Each meal says why it was chosen; Settings shows what was learned, with Start again |
| Cook within your time | Choose the longest a recipe may take on weekdays and at weekends; plans only put recipes on days they fit, and web searches ask for quick ones |
| Keep variety | Automatically, for everyone: no recipe from last week comes back, and at least half of each week is new compared with two weeks before. Choosing a meal yourself is always free |
| Eat a balanced week without setting anything up | Plans aim for a balanced week by default: vegetables most days, fish twice, beans or lentils once, red meat at most twice |
| Add your own preferences | Optional extra rules on top, such as "at least 2 chicken meals a week", enforced by counting; a swap that would break one is flagged |
| Cook once, eat twice | Lets you set portions per meal (Thursday dinner for 3 covers Friday lunch) and scales recipes to match |
| Stop writing grocery lists | Merges all ingredients of the approved plan into one list, grouped by aisle, minus what you always have |
| Add things during the week | Type them in, or say "Hey Siri, add to groceries" |
| Know what's at home | "At home" (in Groceries) lists the food you have, closest to its use-by first. Add it by typing, saying it, or a photo of the fridge; "Put away" after shopping adds the basket. Meals are taken out as their day passes |
| Waste less | Plans prefer recipes that use food at home and share opened packs; the list buys whole packs ("1 bag (300 g), recipes need 200 g") and only what is missing |
| Change your mind | "I'm not cooking this" on any meal, even the day after: its food stays at home and the recipe moves to next week's first free meal, with a warning if fresh food won't keep |
| Save a recipe you saw | Reads it from one or several screenshots, a TikTok or recipe link, a saved cooking video, or pasted text; translates it to English; lets you check it before saving |
| Eat the way you want | Choose one or more diets in Settings (Mediterranean, high protein, low carb, pescatarian, vegetarian, vegan, or your own). Plans and web ideas follow all of them; your own recipes are checked once against each diet. "Update this week" applies a change to an existing plan, keeping the meals that already fit |
| Move meals between days | Drag a meal by its grip onto another day to swap them, or onto an empty day to move it; each day keeps its portions |
| Change a meal fast | A swap button on each meal in the week replaces it in one tap with another recipe that keeps your rules |
| Know what you eat | Shows calories, protein, carbs and fat per portion for every recipe and planned meal; you choose in Settings whether a portion is one serving or a fixed weight (e.g. 400 g) |
| Keep recipes recognisable | Add a photo to any recipe; recipes from websites bring their own photo |
| See how balanced the week is | One calm line on the plan ("Balanced week ✓"); tap it to see each check, including varied proteins |
| Capture a recipe by talking | Record yourself describing it; it is transcribed and turned into a recipe |

## The screens

**Plan** (home). One week at a time, with arrows to move between weeks.
- Each cooked meal shows the recipe, portions and main protein. Meals that are
  new ideas from the web, not from your library, are marked "new idea".
- A row of chips shows where the plan stands against each rule.
- One line shows the week's balance ("Balanced week ✓"); tapping it lists each check.
- Tap a meal to see its ingredients (scaled to the portions) and method, change
  portions, swap it or remove it. Swap options that keep your rules come first;
  the others are marked "breaks a rule".
- **Give me the grocery list** approves the plan and creates the list. Changing
  an approved plan turns it back into a draft until you approve again.
- **Generate a new plan** starts over.

**Recipes**. Your library as one grid, searchable by name or ingredient. Chips filter
by type of dish (main dishes, desserts, breakfasts…) and by protein or tag; one of each
can be combined. Only main dishes are used in the weekly plan.
- **Add recipe** offers six ways: a link (TikTok, recipe website, blog), one or
  several screenshots, saying it out loud, a saved video, pasted text, or typing it.
- Every recipe can have a photo, added or changed in its edit form.
- Anything read by AI opens in the edit form first. Nothing is saved until you
  press Save.
- A recipe page is the read view for cooking; Edit opens the form.
- Recipes sent from the iPhone share sheet are saved straight away and marked
  "check this".

**Groceries**. Two views: "To buy", the shopping list grouped by supermarket aisle,
and "At home", your pantry.
- Items from the plan show the amount and which recipes need them.
- Add items by typing (several at once with commas). Duplicates are skipped.
- Tick items as you shop; they move to "In the basket". **Put away** moves them into
  the pantry; **Clear** just removes them.
- Changes appear on the other phone immediately, and the list keeps working
  with no signal and syncs later.
- Approving a plan again replaces only the items that plan generated. Items you
  typed or added with Siri are never touched.

**Settings**.
- *Meals you cook*: for each lunch and dinner of the week, a switch and a
  portion count. Meals switched off stay blank.
- *Your own extra rules*: optional "at least" or "at most" N meals with a given
  protein or tag, on top of the balanced week.
- *Always in the house*: ingredients left off the generated list.
- *When the plan is ready*: the day and hour next week's plan is made.
- *Allergies*, *Foods you never eat*, *Kitchen equipment*: kept out of plans.
- *Plan-ready notification*: turn on push notifications for this phone.
- *Account*: sign out.

## How it is built

```
web/       TypeScript + React (Vite) + Tailwind, styled from the "Macros App"
           design in Magic Patterns. Installed to the home screen.
backend/   Python + FastAPI, runs on Cloud Run.
  app/core/      Planning, portion scaling, list merging. No database or AI code.
  app/repo/      Storage: Firestore, and an in-memory version for tests.
  app/ai/        The only place that calls Gemini, plus a fake for development.
  app/api/       HTTP routes.
  app/services.py  Use cases that tie the above together.
  app/standards/  The balanced-week rules and food lists, as data. The planner aims for
                 them and the plan screen reports them. Placeholder until a nutritionist
                 reviews them; replacing the file changes both.
firestore.rules  Who may read what directly from the phone.
```

- **Plans are chosen by code, not AI**, so the rules are guaranteed. AI reads
  screenshots, tags and translates recipes, and finds new recipes when the
  library cannot fill the week.
- **New recipes from the web are checked before they appear.** The search only
  proposes pages Google really returned; each page is opened and kept only if it
  loads and has a recipe with ingredients on it. The recipe is built from that
  page; its photo, when it has one, is copied into your Storage when it is saved.
- **Everything belongs to a household**, so a second household later is a new
  record, not a redesign.
- **The web app talks to the API for everything except the grocery list**,
  which it syncs directly with Firestore for live updates and offline use.
- **Types are shared**: `npm run gen:types` generates the web app's types from
  the Python API.

Architecture diagrams and the scaling plan: https://claude.ai/artifact/MdwuZUccyjFqnQQreUXo6X

## Run it locally

No Google account or Firebase project is needed; everything runs against local
emulators with a fake AI. Requires Python 3.12+, Node 22+ and Java (for the emulators).

```bash
npm install -g firebase-tools
firebase emulators:start --project demo-mealplan
```

```bash
cd backend
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099 \
  GOOGLE_CLOUD_PROJECT=demo-mealplan AI_PROVIDER=fake PUSH_ENABLED=false \
  .venv/bin/uvicorn app.asgi:app --port 8000
```

```bash
cd web
npm install
npm run dev
```

Open http://localhost:5173 and choose **Development sign-in**.

## Tests

```bash
cd backend
.venv/bin/pytest
```

With the emulator running, add `FIRESTORE_EMULATOR_HOST=127.0.0.1:8085` to
also run the storage tests against Firestore.

## Putting it on your phone

See [docs/deploy.md](docs/deploy.md).

## What is and is not verified

Tested here, against the Firebase emulators:
- The planning rules, repeat limit, portion scaling and list merging (unit tests).
- Every API route, including sign-in checks and one household not seeing another's data.
- Firestore storage and the security rules.
- The whole flow in a phone-sized browser: settings, adding recipes, generating
  and swapping a plan, the grocery list, and live sync between two phones.

Written but not yet run against the real service, because that needs your
Firebase project:
- **Gemini**: screenshot reading, text import and recipe search. The fake AI
  stood in for it in all tests.
- **Push notifications** and the hourly Cloud Scheduler job delivery.
- **Google sign-in** on a real iPhone, and the two Apple Shortcuts.
- **Deployment** to Cloud Run and Firebase Hosting.

Not built yet:
- Storing the original screenshot alongside an imported recipe.
- Importing Instagram links (Instagram needs an account to read posts; send the
  saved video or a screenshot instead).
- Usage limits on AI calls.
