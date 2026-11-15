"""Diets. Some only steer the web search; some also rule out foods.

A diet is free text ("mediterranean", "high-protein", "low FODMAP"...). The ones
below exclude main proteins, so they also apply to recipes from your library.
"""

_EXCLUDING = {
    "vegetarian": {"vegetarian", "vegan", "egg"},
    "vegan": {"vegan"},
    "pescatarian": {"fish", "seafood", "vegetarian", "vegan", "egg"},
}


def allowed_proteins(diet: str) -> set[str] | None:
    """The main proteins a diet allows, or None if it does not rule any out."""
    return _EXCLUDING.get(diet.strip().lower())


def fits_diet(diet: str, protein: str) -> bool:
    allowed = allowed_proteins(diet)
    return allowed is None or protein in allowed


def search_phrase(diet: str, needs: dict[str, int]) -> str:
    """What to ask the web search for: healthy, varied dinners that fit the diet."""
    diet = diet.strip()
    phrase = (
        f"healthy {diet} home-cooked dinner recipes"
        if diet
        else "healthy home-cooked dinner recipes"
    )
    allowed = allowed_proteins(diet)
    if allowed is None:
        phrase += (
            " with a varied mix of main proteins, such as chicken, fish, seafood, beef, pork, "
            "eggs, and beans or lentils"
        )
    else:
        phrase += " with a varied mix of main ingredients"
    if needs:
        phrase += ", including " + ", ".join(f"at least {n} with {tag}" for tag, n in needs.items())
    return phrase
