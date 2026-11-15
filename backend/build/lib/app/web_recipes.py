"""Find new recipes on the web, keeping only ones whose page really works.

The web search only proposes addresses. Each page is then opened and kept only if
it loads and the AI finds a recipe with ingredients on it. The recipe is built
from that page, so its link is the page that was really read. The page's photo is
used when it has one.
"""

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait

from app.ai.base import AIError, RecipeAI
from app.links import LinkContent, LinkError
from app.models import RecipeDraft

log = logging.getLogger(__name__)

# All pages are opened and read at the same time, so the whole search fits in the
# minute that Firebase Hosting waits for an answer.
MAX_PAGES = 20
# The start of a page is enough to find its recipe, and shorter is much faster to read.
MAX_PAGE_CHARS = 8000


def _check(ai: RecipeAI, read_link: Callable[[str], LinkContent], url: str) -> RecipeDraft | None:
    try:
        content = read_link(url)
    except LinkError as error:
        log.info("Skipped %s: %s", url, error)
        return None
    except Exception:
        log.warning("Skipped %s: unexpected error", url, exc_info=True)
        return None
    try:
        draft = ai.recipe_from_text(content.text[:MAX_PAGE_CHARS], source_url=content.url)
    except AIError as error:
        log.info("Skipped %s: %s", url, error)
        return None
    if not draft.ingredients:
        log.info("Skipped %s: no ingredients found on the page", url)
        return None
    draft.source_url = content.url
    draft.image_url = content.image_url
    return draft


def find_web_recipes(
    ai: RecipeAI,
    read_link: Callable[[str], LinkContent],
    query: str,
    count: int,
    avoid_titles: list[str],
    deadline: float | None = None,
) -> list[RecipeDraft]:
    """Up to ``count`` new recipes for ``query``, each from a page that was checked.

    One web search, then every page found is checked at the same time. Whatever is
    ready by ``deadline`` (a ``time.monotonic()`` value) is returned.
    """
    if deadline is not None and time.monotonic() >= deadline:
        return []
    urls = ai.find_recipe_links(query, count, avoid_titles)[:MAX_PAGES]
    if not urls:
        return []

    pool = ThreadPoolExecutor(max_workers=len(urls))
    futures = [pool.submit(_check, ai, read_link, url) for url in urls]
    remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
    done, not_done = wait(futures, timeout=remaining)
    if not_done:
        log.info("%d of %d pages for %r were not ready in time", len(not_done), len(urls), query)
    # Don't wait for slow pages: their answers are no longer needed.
    pool.shutdown(wait=False, cancel_futures=True)

    avoid = {title.strip().lower() for title in avoid_titles}
    found: list[RecipeDraft] = []
    seen_pages: set[str] = set()
    for future in futures:  # in search order, so the best matches come first
        draft = future.result() if future in done else None
        if draft is None or len(found) >= count:
            continue
        key = draft.title.strip().lower()
        if key in avoid or draft.source_url in seen_pages:
            continue
        avoid.add(key)
        seen_pages.add(draft.source_url or "")
        found.append(draft)
    return found
