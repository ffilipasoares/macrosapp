import { deleteObject, getDownloadURL, ref, uploadBytes } from "firebase/storage";
import { shrinkImage } from "../api";
import { storage } from "../firebase";

/** Upload a recipe photo to Firebase Storage and return its address. */
export async function uploadRecipePhoto(householdId: string, file: File): Promise<string> {
  const image = await shrinkImage(file, 1400);
  const type = image.type || "image/jpeg";
  const extension = type === "image/png" ? "png" : type === "image/webp" ? "webp" : "jpg";
  const id = crypto.randomUUID().replace(/-/g, "");
  const target = ref(storage, `households/${householdId}/recipes/${id}.${extension}`);
  await uploadBytes(target, image, { contentType: type, cacheControl: "public, max-age=31536000" });
  return getDownloadURL(target);
}

/** Remove a photo this app uploaded. Photos from other websites are just forgotten. */
export async function deleteRecipePhoto(url: string | null | undefined): Promise<void> {
  if (!url || !/firebasestorage|127\.0\.0\.1:9199|localhost:9199/.test(url)) return;
  try {
    await deleteObject(ref(storage, url));
  } catch {
    // Already gone, or not ours: nothing to do.
  }
}
