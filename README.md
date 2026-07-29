# Kitchen Macros

Native iOS app (SwiftUI, iOS 17+) for logging recipe and food macros, with voice-driven recipe
capture parsed by Gemini and stored in Firestore.

## Status: Phase 3 — Firebase wiring in the app

- `KitchenMacrosApp.init()` calls `FirebaseApp.configure()`; the root view kicks off anonymous
  sign-in via `AuthService.shared.signInIfNeeded()` in a `.task` on launch.
- Thin Firestore service layer under `KitchenMacros/Services/`: a generic
  `FirestoreCollectionService<T: FirestoreDocument>` (fetch all / fetch by id / add / update /
  delete) shared by `FoodsService`, `RecipesService` (plus `ingredientsService(forRecipeId:)` for
  the `ingredients` subcollection), and `LogEntriesService`. `GoalsService` is separate since
  `goals` is a single fixed document, not a real collection.
- Writes go through `Firestore.Encoder().encode(value)` → the plain dictionary `setData`/
  `addDocument(data:)` calls, **not** the Codable convenience wrappers (`setData(from:)` /
  `addDocument(from:)`) — those only have completion-handler versions in this SDK, no `async`
  variant (confirmed against the actual 11.15.0 source). Reads use `getDocument(as:)` /
  `data(as:)`, which do have native async support.
- Added `FirebaseCore` as an explicit package product dependency (needed for `FirebaseApp` —
  Swift requires every module you `import` to be a direct target dependency, even if another
  linked package already depends on it transitively).
- `ContentView` has a temporary "Write test food to Firestore" button — this is the STOP-gate
  helper below, not permanent UI. It'll be replaced once Phase 4 builds the real Foods screen.

### Phase 3 STOP gate (human)

1. Drag `GoogleService-Info.plist` into the Xcode project navigator (top level of the
   `KitchenMacros` group), check "Copy items if needed" and add it to the `KitchenMacros` target.
2. Build and run on the simulator or your device.
3. Tap "Write test food to Firestore."
4. Check the Firebase console's Firestore data tab — confirm a `foods` document with
   `name: "Test Food"` actually shows up. This is the real proof the app ↔ Firestore connection
   works, not just that the button didn't crash.
5. You can delete the test document from the console afterward.

## Phase 2 — data models & Firestore schema (done, rules deployed)

- `Food`, `Recipe`, `Ingredient`, `LogEntry`, `Goals` Codable structs added under
  `KitchenMacros/Models/`, mirroring the Firestore schema exactly (see brief). They use
  `@DocumentID` from `FirebaseFirestore` (Codable support is built into that module in 11.15.0 —
  no separate `FirebaseFirestoreSwift` package needed).
- Draft Firestore security rules in `firestore.rules` (+ `firebase.json` /
  `firestore.indexes.json` so `firebase deploy --only firestore:rules` works). Single-user app via
  anonymous auth, no per-document ownership field to check — rules require `request.auth != null`
  on every collection and deny everything else by default.

Rules deployed via `firebase deploy --only firestore:rules` and confirmed live in the Firebase
console.

## Phase 1 — project scaffold (done, confirmed building on Xcode 15.4)

- Xcode project `KitchenMacros.xcodeproj` created (SwiftUI App, min deployment target iOS 17,
  Swift 5 language mode). Targets Xcode 15.4 project format (`objectVersion = 60`) to match the
  installed toolchain — Xcode 15.4 ships Swift 5.10, which doesn't support Swift 6 language mode
  or Xcode 16's file-system-synchronized project groups, so this uses the classic explicit
  file-reference project structure instead.
- Firebase iOS SDK (`firebase-ios-sdk`, pinned to `~> 11.15.0`) added as a Swift Package
  dependency, with `FirebaseAuth` and `FirebaseFirestore` linked to the app target.
  **Pinned below 12.0.0 deliberately**: Firebase 12.x bumped its Package.swift to
  `swift-tools-version:6.0`, which needs the Swift 6.0 toolchain (Xcode 16+) just to resolve the
  manifest — Xcode 15.4 fails with "incompatible tools version" if you point it at 12.x. 11.15.0
  is the last release still on `swift-tools-version:5.9`. Re-pin to a 12.x+ version once you
  upgrade to Xcode 16 or later.
- Folder structure: `KitchenMacros/Models`, `Views`, `Services`. New files added to these folders
  need a manual "Add Files to..." step in Xcode (or a pbxproj edit) since this project format
  doesn't auto-sync folder contents like Xcode 16+ does.
- `NSMicrophoneUsageDescription` / `NSSpeechRecognitionUsageDescription` are already set as
  `INFOPLIST_KEY_*` build settings (Phase 6 needs these; harmless to have them from the start).

## Phase 0 prerequisites (done)

Xcode installed (15.4) with Apple ID signed in, Firebase project created with Firestore +
Anonymous Auth enabled on the free Spark plan, `GoogleService-Info.plist` downloaded, Gemini API
key obtained from Google AI Studio.

## Remaining phases

See the build brief for the full phase-by-phase plan: Foods/Goals CRUD (Phase 4), Recipes +
scaling math (Phase 5), voice capture (Phase 6), Gemini ingredient parsing (Phase 7), review
screen (Phase 8), Quick Log (Phase 9), Today screen (Phase 10), editing rules (Phase 11), visual
polish (Phase 12), optional TestFlight (Phase 13).
Each phase ends with a human-verification STOP gate — most of them require a physical iPhone from
Phase 6 onward, since the simulator has no microphone.
