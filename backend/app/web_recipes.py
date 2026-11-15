"""Find new recipes on the web, keeping only ones whose page really works.

The web search only proposes addresses. Each page is then opened and kept only if
it loads and the AI finds a recipe with ingredients on it. The recipe is built
from that page, so its link is the page that was really read. The page's photo is
used when it has one.
"""

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from app.ai.base import AIError, RecipeAI
from app.links import LinkContent, LinkError
from app.models import RecipeDraft

log = logging.getLogger(__name__)

# Pages are checked several at a time, so a plan can be ready within the minute that
# Firebase Hosting waits for an answer.
PARALLEL_CHECKS = 8


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
        draft = ai.recipe_from_text(content.text, source_url=content.url)
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

    No new search or batch of checks starts after ``deadline`` (a ``time.monotonic()``
    value), so the caller gets whatever was found in time.
    """
    if deadline is not None and time.monotonic() >= deadline:
        return []
    urls = ai.find_recipe_links(query, count, avoid_titles)
    avoid = {title.strip().lower() for title in avoid_titles}
    found: list[RecipeDraft] = []
    seen_pages: set[str] = set()

    with ThreadPoolExecutor(max_workers=PARALLEL_CHECKS) as pool:
        position = 0
        while position < len(urls) and len(found) < count:
            if deadline is not None and time.monotonic() >= deadline:
                log.info("Stopped checking pages for %r: out of time", query)
                break
            # Check a few more pages than still needed, since some will not work.
            batch = urls[position : position + max(PARALLEL_CHECKS, count - len(found) + 2)]
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
