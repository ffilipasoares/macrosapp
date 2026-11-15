"""Read a recipe link: a TikTok video's caption, or a recipe web page.

TikTok captions come from TikTok's public oEmbed endpoint (the same one used to
embed videos on other sites), not from scraping the app. Recipe websites
usually describe their recipe in schema.org JSON-LD, which is used when present.

Every address is checked before it is fetched, including after redirects, so a
link can never make the server call itself, Google's metadata server or any
other private address.
"""

import html
import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from urllib.parse import quote, urljoin, urlparse

import httpx

MAX_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
USER_AGENT = "Mozilla/5.0 (compatible; MealPlanner/1.0; personal recipe import)"

TIKTOK_HOSTS = ("tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com")


class LinkError(Exception):
    """The link could not be read. Safe to show to the user."""


@dataclass
class LinkContent:
    url: str
    text: str
    kind: str  # "tiktok", "recipe-data" or "page"
    image_url: str | None = None


def _is_public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    addresses = {info[4][0] for info in infos}
    return bool(addresses) and all(
        ipaddress.ip_address(a.split("%")[0]).is_global for a in addresses
    )


def check_url(url: str) -> str:
    """Return a cleaned URL, or raise if it is not a public http(s) address."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise LinkError("Send a web link that starts with https://")
    if parsed.port not in (None, 80, 443):
        raise LinkError("That link cannot be opened.")
    if not _is_public_host(parsed.hostname):
        raise LinkError("That link cannot be opened.")
    return parsed.geturl()


def fetch(client: httpx.Client, url: str, accept: str = "text/html") -> tuple[str, str]:
    """GET a public URL, following redirects one by one. Returns (final url, body text)."""
    current = check_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        with client.stream(
            "GET",
            current,
            headers={"User-Agent": USER_AGENT, "Accept": accept},
            follow_redirects=False,
        ) as response:
            if response.is_redirect:
                location = response.headers.get("location", "")
                current = check_url(urljoin(current, location))
                continue
            if response.status_code >= 400:
                raise LinkError(f"The page answered with an error ({response.status_code}).")
            body = b""
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    break
            return current, body.decode(response.encoding or "utf-8", errors="replace")
    raise LinkError("The link redirects too many times.")


def is_tiktok(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in TIKTOK_HOSTS or host.endswith(".tiktok.com")


def tiktok_caption(client: httpx.Client, url: str) -> LinkContent:
    final_url, _ = fetch(client, url)  # resolves short vm.tiktok.com links
    endpoint = "https://www.tiktok.com/oembed?url=" + quote(final_url, safe="")
    _, body = fetch(client, endpoint, accept="application/json")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as error:
        raise LinkError("TikTok did not return the video's details.") from error
    caption = str(data.get("title") or "").strip()
    if not caption:
        raise LinkError(
            "This TikTok has no caption to read. Save the video and send the video instead."
        )
    author = str(data.get("author_name") or "").strip()
    text = f"TikTok video by {author}\n\n{caption}" if author else caption
    return LinkContent(url=final_url, text=text, kind="tiktok")


def _find_recipe(node: object) -> dict | None:
    if isinstance(node, list):
        for item in node:
            found = _find_recipe(item)
            if found:
                return found
    elif isinstance(node, dict):
        kind = node.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "Recipe" in kinds:
            return node
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                found = _find_recipe(node[key])
                if found:
                    return found
    return None


def _instructions(value: object) -> list[str]:
    if isinstance(value, str):
        return [line.strip() for line in re.split(r"\n+", _strip_tags(value)) if line.strip()]
    if isinstance(value, list):
        return [step for item in value for step in _instructions(item)]
    if isinstance(value, dict):
        if "itemListElement" in value:
            return _instructions(value["itemListElement"])
        return _instructions(value.get("text") or value.get("name") or "")
    return []


def _image_from(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return _image_from(value[0])
    if isinstance(value, dict):
        return _image_from(value.get("url") or value.get("contentUrl"))
    return None


def page_image(page: str, base_url: str) -> str | None:
    """The recipe's photo: from its schema.org data, else the page's sharing image."""
    image = None
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.S | re.I
    ):
        try:
            recipe = _find_recipe(json.loads(html.unescape(block.strip())))
        except json.JSONDecodeError:
            continue
        if recipe:
            image = _image_from(recipe.get("image"))
            if image:
                break
    if not image:
        for tag in re.findall(r"<meta[^>]+>", page, re.I):
            if re.search(r'(property|name)=["\'](og:image|twitter:image)["\']', tag, re.I):
                match = re.search(r'content=["\']([^"\']+)["\']', tag, re.I)
                if match:
                    image = html.unescape(match.group(1))
                    break
    if not image:
        return None
    image = urljoin(base_url, image.strip())
    return image if image.startswith(("https://", "http://")) and len(image) <= 2000 else None


def recipe_from_json_ld(page: str) -> str | None:
    """The recipe described in a page's schema.org data, as plain text, if there is one."""
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.S | re.I
    ):
        try:
            data = json.loads(html.unescape(block.strip()))
        except json.JSONDecodeError:
            continue
        recipe = _find_recipe(data)
        if not recipe:
            continue
        servings = recipe.get("recipeYield")
        if isinstance(servings, list):
            servings = servings[0] if servings else ""
        lines = [str(recipe.get("name") or "Recipe"), f"Serves: {servings}" if servings else ""]
        if recipe.get("totalTime"):
            lines.append(f"Total time: {recipe['totalTime']}")
        lines.append("\nIngredients:")
        lines += [f"- {_strip_tags(str(i))}" for i in recipe.get("recipeIngredient") or []]
        lines.append("\nMethod:")
        lines += [
            f"{n}. {s}" for n, s in enumerate(_instructions(recipe.get("recipeInstructions")), 1)
        ]
        return "\n".join(line for line in lines if line is not None)
    return None


def _strip_tags(value: str) -> str:
    value = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", value, flags=re.S | re.I)
    value = re.sub(r"<br\s*/?>|</(p|li|h\d|div)>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", value)).strip()


def read_link(url: str, client: httpx.Client | None = None) -> LinkContent:
    own_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    try:
        if is_tiktok(url):
            return tiktok_caption(client, url)
        final_url, page = fetch(client, url)
        image = page_image(page, final_url)
        structured = recipe_from_json_ld(page)
        if structured:
            return LinkContent(url=final_url, text=structured, kind="recipe-data", image_url=image)
        text = _strip_tags(page)
        if len(text) < 80:
            raise LinkError("That page has no readable text. Try a screenshot instead.")
        return LinkContent(url=final_url, text=text[:20000], kind="page", image_url=image)
    except httpx.HTTPError as error:
        raise LinkError("The link could not be opened. Check it and try again.") from error
    finally:
        if own_client:
            client.close()
