# Kitchen Macros

Native iOS app (SwiftUI, iOS 17+) for logging recipe and food macros, with voice-driven recipe
capture parsed by Gemini and stored in Firestore.

## Status: Phase 1 — project scaffold

- Xcode project `KitchenMacros.xcodeproj` created (SwiftUI App, min deployment target iOS 17,
  Swift 5 language mode). Targets Xcode 15.4 project format (`objectVersion = 60`) to match the
  installed toolchain — Xcode 15.4 ships Swift 5.10, which doesn't support Swift 6 language mode
  or Xcode 16's file-system-synchronized project groups, so this uses the classic explicit
  file-reference project structure instead.
- Firebase iOS SDK (`firebase-ios-sdk`, pinned to `~> 11.15.0`) added as a Swift Package
  dependency, with `FirebaseAuth` and `FirebaseFirestore` linked to the app target. Not yet
  initialized in code — that's Phase 3, once `GoogleService-Info.plist` is in place.
  **Pinned below 12.0.0 deliberately**: Firebase 12.x bumped its Package.swift to
  `swift-tools-version:6.0`, which needs the Swift 6.0 toolchain (Xcode 16+) just to resolve the
  manifest — Xcode 15.4 fails with "incompatible tools version" if you point it at 12.x. 11.15.0
  is the last release still on `swift-tools-version:5.9`. Re-pin to a 12.x+ version once you
  upgrade to Xcode 16 or later.
- Folder structure: `KitchenMacros/Models`, `Views`, `Services` (currently placeholders — see the
  README in each). New files added to these folders need a manual "Add Files to..." step in Xcode
  (or a pbxproj edit) since this project format doesn't auto-sync folder contents like Xcode 16+
  does.
- `NSMicrophoneUsageDescription` / `NSSpeechRecognitionUsageDescription` are already set as
  `INFOPLIST_KEY_*` build settings (Phase 6 needs these; harmless to have them from the start).

## Before you open this in Xcode

**Phase 0 prerequisites** (must be done by hand, not verifiable by Claude Code from this
container — it has no macOS/Xcode/network access to Firebase or Google AI Studio):

1. Xcode installed (currently targeting 15.4), Apple ID signed in (free personal team is enough
   for on-device testing).
2. A Firebase project created at console.firebase.google.com with Firestore and Anonymous Auth
   enabled, on the free Spark plan.
3. `GoogleService-Info.plist` downloaded from that project.
4. A Gemini API key from Google AI Studio (ai.google.dev).

## Next step (human, on your Mac)

Open `KitchenMacros.xcodeproj` in Xcode. It should resolve the Firebase package automatically and
build/run on the simulator — **this is the Phase 1 STOP gate: confirm it actually builds before
anything else continues.** Once confirmed, drag in `GoogleService-Info.plist` (Phase 3) — do not
commit that file, it's already gitignored since it contains real project keys.

## Remaining phases

See the build brief for the full phase-by-phase plan (data models & Firestore rules, Firebase
wiring, Foods/Goals CRUD, Recipes + scaling math, voice capture, Gemini ingredient parsing, review
screen, Quick Log, Today screen, editing rules, visual polish, optional TestFlight). Each phase
ends with a human-verification STOP gate — most of them require a physical iPhone from Phase 6
onward, since the simulator has no microphone.
