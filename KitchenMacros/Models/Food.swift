import FirebaseFirestore

/// Macros per 100g, stored in the `foods` collection.
struct Food: Identifiable, FirestoreDocument {
    @DocumentID var id: String?
    var name: String
    var kcal: Double
    var protein: Double
    var carbs: Double
    var fat: Double
}
