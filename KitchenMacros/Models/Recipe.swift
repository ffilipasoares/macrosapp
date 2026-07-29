import FirebaseFirestore

/// Stored in the `recipes` collection; ingredients live in the `ingredients` subcollection.
struct Recipe: Identifiable, FirestoreDocument {
    @DocumentID var id: String?
    var name: String
    var totalWeightGrams: Double
    var servings: Double
    var createdAt: Date
}
