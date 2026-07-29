import SwiftUI

struct ContentView: View {
    @State private var status: String = "Not tested yet."
    private let foodsService = FoodsService()

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "fork.knife.circle")
                .font(.system(size: 56))
                .foregroundStyle(.tint)
            Text("Kitchen Macros")
                .font(.title2.bold())
            Text(status)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            // Phase 3 STOP-gate helper: writes one throwaway "foods" document so you can
            // confirm the Firebase connection in the console. Remove once Phase 4 lands.
            Button("Write test food to Firestore") {
                Task {
                    do {
                        let testFood = Food(name: "Test Food", kcal: 100, protein: 1, carbs: 1, fat: 1)
                        let id = try await foodsService.add(testFood)
                        status = "Wrote test food (id: \(id)). Check Firestore console."
                    } catch {
                        status = "Write failed: \(error.localizedDescription)"
                    }
                }
            }
            .buttonStyle(.borderedProminent)
        }
        .padding()
    }
}

#Preview {
    ContentView()
}
