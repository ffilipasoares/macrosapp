# Meal Planner

A personal app for one weekly routine: decide what to cook, then get the grocery
list for it. Recipes go in once; every Friday the app drafts next week's plan
from them, following your rules; you swap what you don't fancy and tap
**Give me the grocery list**.

It is a web app you add to the iPhone home screen, with a Python backend on
Google Cloud.

## What it does

| You want to | The app |
|---|---|
| Stop planning from a blank page | Drafts a week of meals from your recipe library every Friday and notifies you |
| Keep variety | Uses at most 20% of meals from the previous two weeks, preferring recipes cooked longest ago |
| Follow your own rules | Enforces rules such as "at least 2 chicken and 2 fish meals a week" by counting, and flags a swap that would break one |
| Cook once, eat twice | Lets you set portions per meal (Thursday dinner for 3 covers Friday lunch) and scales recipes to match |
| Stop writing grocery lists | Merges all ingredients of the approved plan into one list, grouped by aisle, minus what you always have |
| Add things during the week | Type them in, or say "Hey Siri, add to groceries" |
| Save a recipe you saw | Reads it from a screenshot or pasted text, translates it to English, and lets you check it before saving |
| Find new ideas | Searches the web for recipes ("healthy dinner with lentils") you can save in one tap |

## The screens

**Plan** (home). One week at a time, with arrows to move between weeks.
- Each cooked meal shows the recipe, portions and main protein. Meals that are
  new ideas from the web, not from your library, are marked "new idea".
- A row of chips shows where the plan stands against each rule.
- Tap a meal to see its ingredients (scaled to the portions) and method, change
  portions, swap it or remove it. Swap options that keep your rules come first;
  the others are marked "breaks a rule".
- **Give me the grocery list** approves the plan and creates the list. Changing
  an approved plan turns it back into a draft until you approve again.
- **Generate a new plan** starts over.

**Recipes**. Your library, searchable by name or ingredient and filterable by protein.
- **Add recipe** offers four ways: a screenshot or photo, pasted text, a web
  search, or typing it yourself.
- Anything read by AI opens in the edit form first. Nothing is saved until you
  press Save.
- A recipe page is the read view for cooking; Edit opens the form.
- Recipes sent from the iPhone share sheet are saved straight away and marked
  "check this".

**Groceries**. The shopping list, grouped by supermarket aisle.
- Items from the plan show the amount and which recipes need them.
- Add items by typing (several at once with commas). Duplicates are skipped.
- Tick items as you shop; they move to "In the basket", which you can clear.
- Changes appear on the other phone immediately, and the list keeps working
  with no signal and syncs later.
- Approving a plan again replaces only the items that plan generated. Items you
  typed or added with Siri are never touched.

**Settings**.
- *Meals you cook*: for each lunch and dinner of the week, a switch and a
  portion count. Meals switched off stay blank.
- *Rules*: "at least" or "at most" N meals with a given protein or tag, plus how
  many weeks to look back for repeats and what share of repeats is allowed.
- *Always in the house*: ingredients left off the generated list.
- *Friday notification*: turn on push notifications for this phone.
- *Siri and the share sheet*: the addresses and private key for the two Apple
  Shortcuts (see [docs/shortcuts.md](docs/shortcuts.md)).
- *Account*: sign out.

## How it is built

```
web/       TypeScript + React (Vite). Installed to the home screen.
backend/   Python + FastAPI, runs on Cloud Run.
  app/core/      Planning, portion scaling, list merging. No database or AI code.
  app/repo/      Storage: Firestore, and an in-memory version for tests.
  app/ai/        The only place that calls Gemini, plus a fake for development.
  app/api/       HTTP routes.
  app/services.py  Use cases that tie the above together.
firestore.rules  Who may read what directly from the phone.
```

- **Plans are chosen by code, not AI**, so the rules are guaranteed. AI reads
  screenshots, tags and translates recipes, and finds new recipes when the
  library cannot fill the week.
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
- **Push notifications** and the Friday Cloud Scheduler job delivery.
- **Google sign-in** on a real iPhone, and the two Apple Shortcuts.
- **Deployment** to Cloud Run and Firebase Hosting.

Not built yet:
- Storing the original screenshot alongside an imported recipe.
- Importing from a link (TikTok and most recipe sites block automated reading;
  use a screenshot or paste the text).
- Usage limits on AI calls.
