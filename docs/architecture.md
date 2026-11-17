# Architecture

What the app is made of today. GitHub shows these diagrams rendered.

## Components

```mermaid
flowchart LR
  subgraph Phone["iPhone"]
    App["Web app<br/>React · installed to home screen"]
    SC["Apple Shortcuts<br/>Siri · share sheet"]
  end

  subgraph Firebase
    Hosting["Hosting<br/>serves the app"]
    Auth["Authentication<br/>Google sign-in"]
    FS[("Firestore<br/>households · recipes · plans · groceries")]
    ST[("Storage<br/>recipe photos")]
    FCM["Cloud Messaging<br/>plan-ready notification"]
  end

  subgraph CloudRun["Cloud Run · Python FastAPI"]
    API["API routes<br/>sign-in · Shortcut key · job token"]
    Core["Core logic<br/>planner · rules · diets · groceries · macros"]
    AIm["AI module<br/>all Gemini calls"]
    Links["Link and page reader<br/>blocks private addresses"]
    Photos["Photo copies<br/>web photos into Storage"]
  end

  Gemini["Vertex AI<br/>Gemini 3.5 Flash + Google Search"]
  Web["The web<br/>recipe sites · TikTok oEmbed"]
  Sched["Cloud Scheduler<br/>every hour"]

  App -->|loads| Hosting
  App -->|signs in| Auth
  App <-->|live grocery list, works offline| FS
  App -->|uploads photos| ST
  App -->|API requests| API
  SC -->|Shortcut key| API
  Sched -->|job token| API
  API --> Core
  API --> AIm
  API --> Links
  API --> Photos
  Core <-->|reads and writes| FS
  AIm --> Gemini
  Links --> Web
  Photos --> Web
  Photos --> ST
  API -->|plan-ready push| FCM
  FCM --> App
```

## Generating a weekly plan

```mermaid
sequenceDiagram
  participant P as Phone
  participant A as API on Cloud Run
  participant F as Firestore
  participant G as Gemini
  participant W as Recipe sites

  P->>A: Generate plan for a week
  A->>F: Settings, recipe library, last two weeks
  A->>G: Check new recipes against the diets (once per recipe)
  A->>A: Pick main dishes by rules, repeats and variety
  alt The library cannot fill the week
    A->>G: Google Search for recipe pages
    A->>W: Open the pages in parallel
    A->>G: Read the pages in batches of 6
    A->>G: Write recipes for any meals still empty
  end
  A->>F: Save the draft plan
  A-->>P: Plan, rule status and notes
  P->>A: Give me the grocery list
  A->>F: Save the list, copy web photos, work out macros
```

## Where things live

| Part | Code | Runs on |
|---|---|---|
| Screens | `web/src` (React, TypeScript, Tailwind) | Firebase Hosting |
| API routes | `backend/app/api` | Cloud Run |
| Planning, rules, diets, groceries, macros | `backend/app/core` (no database or AI code) | Cloud Run |
| Gemini calls | `backend/app/ai/gemini.py` | Cloud Run, calling Vertex AI |
| Web search and page reading | `backend/app/web_recipes.py`, `backend/app/links.py` | Cloud Run |
| Data | `backend/app/repo/firestore.py`, `firestore.rules`, `storage.rules` | Firestore, Storage |
| Tests and checks | `backend/tests`, `.github/workflows/ci.yml` | GitHub Actions |
