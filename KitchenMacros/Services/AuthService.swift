import Combine
import FirebaseAuth

@MainActor
final class AuthService: ObservableObject {
    static let shared = AuthService()

    @Published private(set) var userID: String?

    private init() {
        userID = Auth.auth().currentUser?.uid
    }

    /// Signs in anonymously on first launch; on later launches Firebase Auth already has a
    /// persisted session, so this just picks up the existing uid.
    func signInIfNeeded() async throws {
        if let user = Auth.auth().currentUser {
            userID = user.uid
            return
        }
        let result = try await Auth.auth().signInAnonymously()
        userID = result.user.uid
    }
}
