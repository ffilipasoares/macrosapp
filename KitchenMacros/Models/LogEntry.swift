import FirebaseFirestore

enum LogSourceType: String, Codable {
    case recipe
    case food
    case aiEstimate
}

/// Stored in the `logEntries` collection.
struct LogEntry: Identifiable, Codable {
    @DocumentID var id: String?
    var date: Date
    var sourceType: LogSourceType
    var sourceId: String?
    var name: String
    var grams: Double
    var kcal: Double
    var protein: Double
    var carbs: Double
    var fat: Double
    var createdAt: Date
}
