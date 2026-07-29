struct FoodsService {
    private let collection = FirestoreCollectionService<Food>(path: "foods")

    func fetchAll() async throws -> [Food] {
        try await collection.fetchAll()
    }

    @discardableResult
    func add(_ food: Food) async throws -> String {
        try await collection.add(food)
    }

    func update(_ food: Food) async throws {
        try await collection.update(food)
    }

    func delete(id: String) async throws {
        try await collection.delete(id: id)
    }
}
