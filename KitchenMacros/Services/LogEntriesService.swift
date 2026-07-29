struct LogEntriesService {
    private let collection = FirestoreCollectionService<LogEntry>(path: "logEntries")

    func fetchAll() async throws -> [LogEntry] {
        try await collection.fetchAll()
    }

    @discardableResult
    func add(_ entry: LogEntry) async throws -> String {
        try await collection.add(entry)
    }

    func update(_ entry: LogEntry) async throws {
        try await collection.update(entry)
    }

    func delete(id: String) async throws {
        try await collection.delete(id: id)
    }
}
