"""Find new recipes on the web, keeping only ones whose page really works.

The web search only proposes addresses. Each page is then opened and kept only if
it is a real recipe website's page: not a code site, forum, video or social network,
and it publishes proper recipe data (the schema.org Recipe markup recipe sites use),
which the AI then reads into a recipe with ingredients. The recipe is built
from that page, so its link is the page that was really read. The page's photo is
used when it has one.
"""

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
from urllib.parse import urlsplit

from app.ai.base import AIError, RecipeAI
from app.links import LinkContent, LinkError
from app.models import RecipeDraft

log = logging.getLogger(__name__)

# Pages are opened and read concurrently with bounded workers so the whole search
# fits in the minute that Firebase Hosting waits without overwhelming a 1-CPU instance.
MAX_PAGES = 16
MAX_WORKERS = 6
# The start of a page is enough to find its recipe, and shorter is much faster to read.
MAX_PAGE_CHARS = 8000
# Downloads stop this long before the deadline, so the pages that did load can still be read.
READ_RESERVE_SECONDS = 15.0


# Never recipe websites, even when a page there happens to contain a recipe.
NOT_RECIPE_SITES = (
    "github.com", "githubusercontent.com", "gitlab.com", "bitbucket.org", "gist.github.com",
    "stackoverflow.com", "stackexchange.com", "reddit.com", "quora.com", "wikipedia.org",
    "wikihow.com", "youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com",
    "pinterest.com", "pinterest.pt", "x.com", "twitter.com", "medium.com", "substack.com",
    "docs.google.com", "drive.google.com", "amazon.com", "amazon.es", "archive.org",
    "scribd.com", "slideshare.net", "pdfcoffee.com", "chatgpt.com", "openai.com",
)  # fmt: skip


def is_recipe_website(content: LinkContent) -> bool:
    """A page from a real recipe website: publishes recipe data and is not a blocked site."""
    host = (urlsplit(content.url).hostname or "").lower()
    blocked = any(host == site or host.endswith("." + site) for site in NOT_RECIPE_SITES)
    return content.kind == "recipe-data" and not blocked


def _fetch_page(
    read_link: Callable[[str], LinkContent],
    url: str,
    deadline: float | None = None,
) -> LinkContent | None:
    if deadline is not None and time.monotonic() >= deadline:
        return None
    try:
        return read_link(url)
    except LinkError as error:
        log.info("Skipped %s: %s", url, error)
        return None
    except Exception:
        log.warning("Skipped %s: unexpected error", url, exc_info=True)
        return None


def _extract_draft(ai: RecipeAI, content: LinkContent) -> RecipeDraft | None:
    try:
        draft = ai.recipe_from_text(content.text[:MAX_PAGE_CHARS], source_url=content.url)
    except AIError as error:
        log.info("Skipped %s: %s", content.url, error)
        return None
    if not draft.ingredients:
        log.info("Skipped %s: no ingredients found on the page", content.url)
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

    One web search, then pages are downloaded concurrently and read in a single batch
    AI call when supported. Whatever is ready by ``deadline`` is returned.
    """
    if deadline is not None and time.monotonic() >= deadline:
        return []
    urls = ai.find_recipe_links(query, count, avoid_titles)[:MAX_PAGES]
    if not urls:
        return []

    fetch_deadline = None if deadline is None else deadline - READ_RESERVE_SECONDS
    pool = ThreadPoolExecutor(max_workers=min(8, len(urls)))
    futures = [pool.submit(_fetch_page, read_link, url, fetch_deadline) for url in urls]
    remaining = None if fetch_deadline is None else max(0.0, fetch_deadline - time.monotonic())
    done, not_done = wait(futures, timeout=remaining)
    if not_done:
        log.info("%d of %d pages for %r were not ready in time", len(not_done), len(urls), query)
    pool.shutdown(wait=False, cancel_futures=True)

    contents = [
        content for future in futures if future in done and (content := future.result()) is not None
    ]
    skipped = [c.url for c in contents if not is_recipe_website(c)]
    if skipped:
        log.info("Skipped pages that are not recipe websites: %s", skipped)
    contents = [content for content in contents if is_recipe_website(content)]
    if not contents or (deadline is not None and time.monotonic() >= deadline):
        return []

    batch_fn = getattr(ai, "recipes_from_pages", None)
    if callable(batch_fn):
        try:
            raw_drafts = batch_fn([(c.text[:MAX_PAGE_CHARS], c.url) for c in contents])
        except AIError as error:
            log.info("Batch recipe extraction failed for %r: %s", query, error)
            return []
        drafts: list[RecipeDraft | None] = []
        for content, draft in zip(contents, raw_drafts, strict=False):
            if draft is not None and draft.ingredients:
                draft.source_url = content.url
                draft.image_url = content.image_url
                drafts.append(draft)
            else:
                drafts.append(None)
    else:
        drafts = [_extract_draft(ai, content) for content in contents]

    avoid = {title.strip().lower() for title in avoid_titles}
    found: list[RecipeDraft] = []
    seen_pages: set[str] = set()
    for draft in drafts:  # in search order, so the best matches come first
        if draft is None or len(found) >= count:
            continue
        key = draft.title.strip().lower()
        if key in avoid or draft.source_url in seen_pages:
            continue
        avoid.add(key)
        seen_pages.add(draft.source_url or "")
        found.append(draft)
    return found
