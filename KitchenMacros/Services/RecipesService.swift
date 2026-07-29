struct RecipesService {
    private let collection = FirestoreCollectionService<Recipe>(path: "recipes")

    func fetchAll() async throws -> [Recipe] {
        try await collection.fetchAll()
    }

    @discardableResult
    func add(_ recipe: Recipe) async throws -> String {
        try await collection.add(recipe)
    }

    func update(_ recipe: Recipe) async throws {
        try await collection.update(recipe)
    }

    func delete(id: String) async throws {
        try await collection.delete(id: id)
    }

    func ingredientsService(forRecipeId recipeId: String) -> FirestoreCollectionService<Ingredient> {
        FirestoreCollectionService(path: "recipes/\(recipeId)/ingredients")
    }
}
