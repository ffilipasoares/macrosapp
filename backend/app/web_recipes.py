"""Find new recipes on the web, keeping only ones whose page really works.

The web search only proposes addresses. Each page is then opened and kept only if
it loads, describes a single recipe in structured recipe data, and has a photo.
The recipe is built from that page, so its link is the page that was really read.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from app.ai.base import AIError, RecipeAI
from app.links import LinkContent, LinkError
from app.models import RecipeDraft

log = logging.getLogger(__name__)

PARALLEL_CHECKS = 4


def _check(ai: RecipeAI, read_link: Callable[[str], LinkContent], url: str) -> RecipeDraft | None:
    try:
        content = read_link(url)
    except LinkError as error:
        log.info("Skipped %s: %s", url, error)
        return None
    except Exception:
        log.warning("Skipped %s: unexpected error", url, exc_info=True)
        return None
    if content.kind not in ("recipe-data", "tiktok") or not content.image_url:
        log.info("Skipped %s: not a single recipe with a photo", url)
        return None
    try:
        draft = ai.recipe_from_text(content.text, source_url=content.url)
    except AIError as error:
        log.info("Skipped %s: %s", url, error)
        return None
    if not draft.ingredients:
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
) -> list[RecipeDraft]:
    """Up to ``count`` new recipes for ``query``, each from a page that was checked."""
    urls = ai.find_recipe_links(query, count, avoid_titles)
    avoid = {title.strip().lower() for title in avoid_titles}
    found: list[RecipeDraft] = []
    seen_pages: set[str] = set()

    with ThreadPoolExecutor(max_workers=PARALLEL_CHECKS) as pool:
        position = 0
        while position < len(urls) and len(found) < count:
            # Check a few more pages than still needed, since some will not work.
            batch = urls[position : position + max(PARALLEL_CHECKS, count - len(found) + 1)]
            position += len(batch)
            for draft in pool.map(lambda url: _check(ai, read_link, url), batch):
                if draft is None or len(found) >= count:
                    continue
                key = draft.title.strip().lower()
                if key in avoid or draft.source_url in seen_pages:
                    continue
                avoid.add(key)
                seen_pages.add(draft.source_url or "")
                found.append(draft)
    return found
