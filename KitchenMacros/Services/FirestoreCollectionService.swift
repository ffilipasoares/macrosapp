import FirebaseFirestore

/// Conformance shared by every top-level model so the generic service below can read/write it.
/// `@DocumentID var id: String?` satisfies this even though it's a property wrapper.
protocol FirestoreDocument: Codable {
    var id: String? { get set }
}

enum FirestoreServiceError: Error {
    case missingDocumentID
}

/// Thin read/write layer over a single Firestore collection, shared by the per-collection
/// services below instead of repeating the same CRUD calls four times.
struct FirestoreCollectionService<T: FirestoreDocument> {
    private let collectionRef: CollectionReference

    init(collectionRef: CollectionReference) {
        self.collectionRef = collectionRef
    }

    init(path: String, firestore: Firestore = .firestore()) {
        self.init(collectionRef: firestore.collection(path))
    }

    func fetchAll() async throws -> [T] {
        let snapshot = try await collectionRef.getDocuments()
        return snapshot.documents.compactMap { try? $0.data(as: T.self) }
    }

    func fetch(id: String) async throws -> T {
        try await collectionRef.document(id).getDocument(as: T.self)
    }

    @discardableResult
    func add(_ value: T) async throws -> String {
        let data = try Firestore.Encoder().encode(value)
        let ref = try await collectionRef.addDocument(data: data)
        return ref.documentID
    }

    func update(_ value: T) async throws {
        guard let id = value.id else { throw FirestoreServiceError.missingDocumentID }
        let data = try Firestore.Encoder().encode(value)
        try await collectionRef.document(id).setData(data)
    }

    func delete(id: String) async throws {
        try await collectionRef.document(id).delete()
    }
}
