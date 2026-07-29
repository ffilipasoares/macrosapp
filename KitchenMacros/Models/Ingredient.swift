import FirebaseFirestore

/// Stored in the `recipes/{recipeId}/ingredients` subcollection.
struct Ingredient: Identifiable, Codable {
    @DocumentID var id: String?
    var name: String
    var foodId: String?
    var grams: Double
}
