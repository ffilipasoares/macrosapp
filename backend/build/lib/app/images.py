"""Keep our own copy of recipe photos that come from the web.

Web pages change and TikTok's image links expire after a few days, so when a
recipe from the internet is saved, its photo is copied into the household's
folder in Firebase Storage. The copy is served the same way as photos uploaded
from the app: a download link carrying an unguessable token.
"""

import logging
from collections.abc import Callable
from typing import Protocol
from urllib.parse import quote
from uuid import uuid4

from app.models import Recipe

log = logging.getLogger(__name__)

_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}


class ImageStore(Protocol):
    def owns(self, url: str) -> bool:
        """Whether the photo at this address is already one of ours."""
        ...

    def save(self, household_id: str, data: bytes, content_type: str) -> str:
        """Store a photo and return the address to show it from."""
        ...


class FirebaseImageStore:
    def __init__(self, bucket_name: str) -> None:
        from firebase_admin import storage

        self.bucket_name = bucket_name
        self.bucket = storage.bucket(bucket_name)

    def owns(self, url: str) -> bool:
        return f"/b/{self.bucket_name}/o/" in url

    def save(self, household_id: str, data: bytes, content_type: str) -> str:
        extension = _EXTENSIONS.get(content_type, "jpg")
        path = f"households/{household_id}/recipes/{uuid4().hex}.{extension}"
        token = uuid4().hex
        blob = self.bucket.blob(path)
        # The same kind of download token the Firebase apps create, so the link works in <img>.
        blob.metadata = {"firebaseStorageDownloadTokens": token}
        blob.cache_control = "public, max-age=31536000"
        blob.upload_from_string(data, content_type=content_type)
        return (
            f"https://firebasestorage.googleapis.com/v0/b/{self.bucket_name}/o/"
            f"{quote(path, safe='')}?alt=media&token={token}"
        )


class MemoryImageStore:
    """For tests and local development."""

    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}

    def owns(self, url: str) -> bool:
        return url.startswith("https://images.test/")

    def save(self, household_id: str, data: bytes, content_type: str) -> str:
        url = f"https://images.test/{household_id}/{uuid4().hex}"
        self.saved[url] = data
        return url


def keep_own_copy(
    store: ImageStore | None,
    read_image: Callable[[str], tuple[bytes, str]],
    household_id: str,
    recipe: Recipe,
) -> None:
    """Replace a web photo address with our own copy. Keeps the web address if copying fails."""
    url = recipe.image_url
    if store is None or not url or store.owns(url):
        return
    try:
        data, content_type = read_image(url)
        recipe.image_url = store.save(household_id, data, content_type)
    except Exception:
        log.warning("Could not keep a copy of the photo for %r", recipe.title, exc_info=True)
