import FirebaseFirestore

/// `goals` is a single fixed document, not a real collection, so it doesn't go through
/// `FirestoreCollectionService` — there's no list of goals and no document id to track.
struct GoalsService {
    private let docRef = Firestore.firestore().collection("goals").document("current")

    func fetch() async throws -> Goals? {
        try await docRef.getDocument(as: Goals?.self)
    }

    func save(_ goals: Goals) async throws {
        let data = try Firestore.Encoder().encode(goals)
        try await docRef.setData(data)
    }
}
