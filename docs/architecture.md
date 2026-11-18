# Architecture

What the app is made of today. GitHub shows these diagrams rendered.

## Components

```mermaid
flowchart LR
  subgraph Phone["iPhone"]
    App["Web app<br/>React · home screen<br/>English or Portuguese"]
    SC["Apple Shortcuts<br/>Siri · share sheet"]
  end

  subgraph Firebase
    Hosting["Hosting<br/>serves the app"]
    Auth["Authentication<br/>Google sign-in"]
    FS[("Firestore<br/>households · settings · recipes<br/>plans · groceries · pantry · taste")]
    ST[("Storage<br/>recipe photos")]
    FCM["Cloud Messaging<br/>plan-ready notification"]
  end

  subgraph CloudRun["Cloud Run · Python FastAPI"]
    API["API routes<br/>sign-in · Shortcut key · job token"]
    Services["Services<br/>plans · pantry · taste · language"]
    Core["Core logic, no AI or database<br/>planner · balance · variety · diets<br/>allergens · groceries · packs · pantry · taste"]
    AIm["AI module<br/>all Gemini calls"]
    Links["Link and page reader<br/>blocks private addresses"]
    Std["Data files<br/>balanced-week standards · pack sizes"]
  end

  Gemini["Vertex AI<br/>Gemini Flash + Google Search"]
  Web["The web<br/>recipe sites · TikTok"]
  Sched["Cloud Scheduler<br/>every hour"]
  Tasks["Cloud Tasks<br/>queue: plans"]

  App -->|loads| Hosting
  App -->|signs in| Auth
  App <-->|live grocery list, offline| FS
  App -->|uploads photos| ST
  App -->|API requests| API
  SC -->|Shortcut key| API
  Sched -->|job token| API
  API -->|queues a plan| Tasks
  Tasks -->|job token, up to 15 min| API
  API --> Services
  Services --> Core
  Core --> Std
  Services --> AIm
  Services --> Links
  Services <-->|reads and writes| FS
  AIm --> Gemini
  Links --> Web
  Services -->|plan ready| FCM
  FCM --> App
```

## Making a weekly plan

Plans are made in the background so no request runs into Firebase Hosting's
one-minute limit.

```mermaid
sequenceDiagram
  participant P as Phone
  participant A as API on Cloud Run
  participant Q as Cloud Tasks
  participant F as Firestore
  participant G as Gemini
  participant W as Recipe sites

  P->>A: Generate plan for a week
  A->>F: Mark the week "generating"
  A->>Q: Queue the job
  A-->>P: The week, marked generating
  loop every 3 seconds
    P->>A: Get the plan
  end
  Q->>A: Run the job (job token)
  A->>F: Settings, library, last two weeks, pantry, taste
  A->>G: Check recipes against diets and allergies (once each)
  A->>A: Pick by rules, variety, cooking time, taste, food at home
  alt The library cannot fill the week
    A->>G: Google Search for recipe pages
    A->>W: Open the pages in parallel
    A->>G: Read the pages; write recipes for any meals still empty
  end
  A->>G: Translate new ideas (Portuguese households)
  A->>F: Save the plan (generating cleared)
  P->>A: Get the plan: done
```

Without a Cloud Tasks queue configured (locally, in tests), the job runs inside the
request instead.

## How the planner decides

Each step only chooses among what the steps above it allow.

```mermaid
flowchart TB
  A["Allergies, foods never eaten, equipment, diets<br/>(never broken)"] --> B
  B["Cooking time per day<br/>(a recipe only goes on a day it fits)"] --> C
  C["Variety: nothing from last week,<br/>at most half from two weeks ago"] --> D
  D["Balanced week: vegetables most days, fish ×2,<br/>legumes ×1, red meat ≤2 (standards file)"] --> E
  E["Your own extra rules<br/>(e.g. at least 2 chicken)"] --> F
  F["Taste + food at home<br/>(one pick in five: something new)"] --> G
  G["Shared fresh food, then cooked longest ago"]
```

Choosing a meal by hand is always free: any recipe can be picked, with warnings
only for allergies, foods never eaten, equipment and diets.

## Data

```mermaid
erDiagram
  HOUSEHOLD ||--|| SETTINGS : has
  HOUSEHOLD ||--o{ RECIPE : keeps
  HOUSEHOLD ||--o{ PLAN : "one per week"
  HOUSEHOLD ||--o{ GROCERY_ITEM : lists
  HOUSEHOLD ||--|| PANTRY : has
  HOUSEHOLD ||--|| TASTE : learns
  PLAN ||--o{ MEAL : "per slot"
  MEAL }o--|| RECIPE : "copy of"
  HOUSEHOLD {
    list members
    bool setup_done
    string shortcut_token
  }
  SETTINGS {
    string language
    map slots
    list rules
    list diets
    list allergies
    list avoid
    list equipment
    string plan_day
    int cook_minutes_weekday
    int cook_minutes_weekend
  }
  RECIPE {
    string language
    list ingredients "English name + label"
    bool liked
    bool not_for_us
    map diet_fit
  }
  PLAN {
    string week_id
    string status
    datetime generating_since
    bool pending
    bool put_away
  }
  PANTRY {
    list items "name, label, amount, use_by"
  }
  TASTE {
    map scores "fading"
    list blocked
  }
```

Ingredient names are always English underneath (allergies, the pantry, packs and
diets match on them); `label` shows them in Portuguese households.

## Where things live

| Part | Code | Runs on |
|---|---|---|
| Screens | `web/src` (React, TypeScript, Tailwind); Portuguese in `web/src/lib/i18n-pt.ts` | Firebase Hosting |
| API routes | `backend/app/api` | Cloud Run |
| Use cases | `backend/app/services.py` | Cloud Run |
| Planning, rules, variety, balance, diets, allergens, groceries, packs, pantry, taste | `backend/app/core` (no database or AI code) | Cloud Run |
| Background plans | `backend/app/tasks.py` | Cloud Run + Cloud Tasks |
| Gemini calls | `backend/app/ai/gemini.py` (`fake.py` for tests and local runs) | Vertex AI |
| Web search and page reading | `backend/app/web_recipes.py`, `backend/app/links.py` | Cloud Run |
| Balanced-week guidance (placeholder) | `backend/app/standards/default.json` | data |
| Pack sizes | `backend/app/data/packs.json` | data |
| Backend's own words in two languages | `backend/app/i18n.py` | Cloud Run |
| Data | `backend/app/repo/firestore.py`, `firestore.rules`, `storage.rules` | Firestore, Storage |
| Tests and checks | `backend/tests`, `.github/workflows/ci.yml` | GitHub Actions |
