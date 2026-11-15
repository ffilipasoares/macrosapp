# Putting the app on your phone

These steps have not been run end to end yet; they need your Google account.
Expect to adjust small details the first time. Replace `PROJECT` with your
Firebase project id throughout.

## 1. Create the project (once)

1. In the [Firebase console](https://console.firebase.google.com), create a
   project and switch it to the **Blaze** (pay as you go) plan. At personal use
   the cost should be close to zero; set a budget alert in Google Cloud Billing.
2. **Authentication** → Sign-in method → enable **Google**.
3. **Firestore Database** → create it in a European location, production mode.
   Then **Storage** → **Get started** (production mode, same region), for recipe photos.
4. **Project settings → General → Your apps** → add a **Web app** and keep the
   config values for step 3.
5. **Project settings → Cloud Messaging → Web Push certificates** → generate a
   key pair.
6. In Google Cloud, enable the **Vertex AI API** and the **Cloud Run**,
   **Cloud Build** and **Cloud Scheduler** APIs.

```bash
npm install -g firebase-tools
firebase login
firebase use --add PROJECT
gcloud config set project PROJECT
```

## 2. Deploy the backend

Pick a long random value for the scheduler secret:

```bash
openssl rand -hex 32
```

```bash
gcloud run deploy mealplan-api \
  --source backend \
  --region europe-west1 \
  --memory 1Gi \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=PROJECT,ALLOWED_EMAILS=you@example.com,APP_URL=https://PROJECT.web.app,JOB_TOKEN=THE_RANDOM_VALUE,STORAGE_BUCKET=PROJECT.firebasestorage.app"
```

- `ALLOWED_EMAILS` is the shared Google account. Nobody else can sign in.
- `--allow-unauthenticated` lets the phone reach the service; every route still
  checks the signed-in user, the Shortcut key or the scheduler secret itself.
- `GEMINI_MODEL` defaults to `gemini-2.5-flash` and `GEMINI_LOCATION` to
  `europe-west1`. Check the current model names in the Vertex AI console and
  override with `--set-env-vars` if that one has been retired.

- `STORAGE_BUCKET` is your Storage bucket (the `storageBucket` value in the web
  app config). Photos of recipes taken from the web are copied there when you
  save them, so they keep working after the website or TikTok link changes.
  Without it, those photos are shown from the original website.

The service account Cloud Run uses needs these roles (IAM → grant):
**Cloud Datastore User**, **Vertex AI User**,
**Firebase Cloud Messaging API Admin** and **Storage Object Admin**.

## 3. Deploy the web app and database rules

```bash
cd web
cp .env.example .env.local
```

Fill in `.env.local` from step 1.4 and 1.5, including
`VITE_FIREBASE_STORAGE_BUCKET` (the `storageBucket` value, usually
`PROJECT.firebasestorage.app`). The first `storage` deploy asks to let Storage
read Firestore, so the photo rules can check household membership; answer yes. Set
`VITE_FIREBASE_AUTH_DOMAIN=PROJECT.web.app` (the address the app is served
from), which keeps Google sign-in working inside an installed iPhone app.

```bash
npm install
npm run build
cd ..
firebase deploy --only hosting,firestore,storage
```

The app is now at `https://PROJECT.web.app`.

## 3b. Let planning take longer than a minute

Firebase Hosting stops any request after 60 seconds, which can cut the web search
short ("The web search ran out of time"). To avoid that, the app can call the
backend directly at its Cloud Run address:

1. In `web/.env.local`, set `VITE_API_URL` to the Cloud Run address printed by
   `gcloud run deploy` (for example `https://mealplan-api-abc123-ew.a.run.app`),
   then build and deploy the web app again.
2. Allow the app's addresses to call the backend, and give the search its budget:

```bash
gcloud run services update mealplan-api --region europe-west1 --update-env-vars "^;^CORS_ORIGINS=https://PROJECT.web.app,https://PROJECT.firebaseapp.com;WEB_SEARCH_SECONDS=100"
```

`WEB_SEARCH_SECONDS` is how long the web search may run (default 100). Without
`VITE_API_URL`, keep it at 50 or less.

## 4. Schedule the Friday plan

Use the Cloud Run address printed in step 2, not the web.app address:

```bash
gcloud scheduler jobs create http weekly-plan \
  --location europe-west1 \
  --schedule "0 17 * * 5" \
  --time-zone "Europe/Lisbon" \
  --uri "https://YOUR-CLOUD-RUN-URL/api/jobs/weekly-plan" \
  --http-method POST \
  --headers "X-Job-Token=THE_RANDOM_VALUE"
```

That is 17:00 every Friday, Lisbon time. Running it twice in a week is safe:
an existing plan for next week is left alone.

## 5. On each iPhone

1. Open `https://PROJECT.web.app` in Safari.
2. Share → **Add to Home Screen**, then open the app from the home screen.
3. Sign in with the shared Google account.
4. Settings → **Turn on notifications**.
5. Set up the two Shortcuts: [shortcuts.md](shortcuts.md).

## Later: a separate development environment

Create a second Firebase project and repeat steps 1 to 3 with it. Deploy the
`development` branch there and `main` to the real one, so experiments never
touch your real plans.
