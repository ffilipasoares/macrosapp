import FirebaseFirestore

/// Stored as a single document in the `goals` collection.
struct Goals: Codable {
    var dailyKcal: Double
    var dailyProtein: Double
    var dailyCarbs: Double
    var dailyFat: Double
}
