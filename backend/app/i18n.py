"""The backend's own words, in English and Portuguese (Portugal).

Only text the backend writes for people: plan notes, warnings, labels on the grocery
list, rule and balance labels, notifications. The screens have their own catalogue in
the web app. Error messages from failures stay in English for now.
"""

DAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "pt": ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
           "sábado", "domingo"],
}  # fmt: skip
MEALS = {
    "en": {"lunch": "lunch", "dinner": "dinner"},
    "pt": {"lunch": "almoço", "dinner": "jantar"},
}

ALLERGENS_PT = {
    "gluten": "glúten", "milk": "leite", "eggs": "ovos", "fish": "peixe",
    "crustaceans": "crustáceos", "molluscs": "moluscos", "peanuts": "amendoins",
    "tree nuts": "frutos de casca rija", "soy": "soja", "sesame": "sésamo", "celery": "aipo",
    "mustard": "mostarda", "lupin": "tremoço", "sulphites": "sulfitos",
}  # fmt: skip
EQUIPMENT_PT = {
    "oven": "um forno", "air fryer": "uma air fryer", "microwave": "um micro-ondas",
    "slow cooker": "uma panela de cozedura lenta", "pressure cooker": "uma panela de pressão",
    "blender": "uma liquidificadora", "grill": "um grelhador",
}  # fmt: skip
PACKS_PT = {
    "pack": ("embalagem", "embalagens"), "bag": ("saco", "sacos"), "box": ("caixa", "caixas"),
    "tin": ("lata", "latas"), "carton": ("pacote", "pacotes"), "pot": ("pote", "potes"),
    "ball": ("bola", "bolas"), "piece": ("pedaço", "pedaços"),
    "box of 6": ("caixa de 6", "caixas de 6"), "pack of 8": ("embalagem de 8", "embalagens de 8"),
}  # fmt: skip

# Protein and tag words used in rule labels.
WORDS_PT = {
    "chicken": "frango", "fish": "peixe", "seafood": "marisco", "beef": "vaca", "pork": "porco",
    "lamb": "borrego", "turkey": "peru", "egg": "ovo", "vegetarian": "vegetariano",
    "vegan": "vegano", "vegetables": "legumes", "legumes": "leguminosas",
    "red meat": "carne vermelha", "quick": "rápido", "pasta": "massa", "soup": "sopa",
}  # fmt: skip

_MESSAGES: dict[str, dict[str, str]] = {
    "diet_check_failed": {
        "en": "Could not check your recipes against your diets: {error}",
        "pt": "Não foi possível verificar as receitas face às tuas dietas: {error}",
    },
    "search_failed": {
        "en": "Could not look for new recipes: {error}",
        "pt": "Não foi possível procurar receitas novas: {error}",
    },
    "search_timeout": {
        "en": "The web search ran out of time ({seconds:g} seconds) before finding enough "
        "recipes, so some meals are empty. Choose them yourself, or generate again.",
        "pt": "A pesquisa na web demorou demasiado ({seconds:g} segundos) e não encontrou "
        "receitas suficientes, por isso há refeições vazias. Escolhe-as tu ou gera de novo.",
    },
    "empty_library": {
        "en": "Only {filled} of {total} meals could be filled: your recipe library is empty "
        "and the web search did not find enough. Add a few recipes, or try again.",
        "pt": "Só foi possível preencher {filled} de {total} refeições: ainda não tens receitas "
        "e a pesquisa na web não encontrou o suficiente. Junta algumas receitas ou tenta de novo.",
    },
    "not_filled": {
        "en": "Only {filled} of {total} meals could be filled with recipes that fit your diets, "
        "allergies and rules. Add more recipes, or choose the empty meals yourself.",
        "pt": "Só foi possível preencher {filled} de {total} refeições com receitas que respeitam "
        "as tuas dietas, alergias e regras. Junta mais receitas ou escolhe tu as que faltam.",
    },
    "approve_again": {
        "en": "Approve the plan again to update your grocery list.",
        "pt": "Aprova o plano de novo para atualizar a lista de compras.",
    },
    "contains": {"en": "contains {food}", "pt": "contém {food}"},
    "needs": {"en": "needs {item}", "pt": "precisa de {item}"},
    "plan_ready_title": {"en": "Meal plan ready", "pt": "Plano de refeições pronto"},
    "plan_ready_body": {
        "en": "Your meal plan for next week is ready.",
        "pt": "O plano de refeições da próxima semana está pronto.",
    },
    "bought_for": {"en": "bought for {day}'s {title}", "pt": "comprado para {title} de {day}"},
    "wont_keep": {
        "en": "The {food} won't keep until {day}. Freeze it, or cook this sooner.",
        "pt": "{food} não aguenta até {day}. Congela, ou cozinha isto mais cedo.",
    },
    "have_some": {"en": "you have some at home", "pt": "tens algum em casa"},
    "rest_at_home": {"en": "the rest is at home", "pt": "o resto está em casa"},
    "at_least": {"en": "At least {count} {what}", "pt": "Pelo menos {count} {what}"},
    "at_most": {"en": "At most {count} {what}", "pt": "No máximo {count} {what}"},
    "repeats": {
        "en": "Nothing from last week, at most {count} from two weeks ago",
        "pt": "Nada da semana passada, no máximo {count} de há duas semanas",
    },
    "check_vegetable_days": {"en": "Vegetables most days", "pt": "Legumes na maioria dos dias"},
    "check_fish": {"en": "Fish or seafood", "pt": "Peixe ou marisco"},
    "check_legumes": {"en": "Beans, lentils or chickpeas", "pt": "Feijão, lentilhas ou grão"},
    "check_red_meat": {"en": "Red meat", "pt": "Carne vermelha"},
    "check_protein_variety": {"en": "Different proteins", "pt": "Proteínas diferentes"},
    "days_of": {"en": "{value} of {days} days", "pt": "{value} de {days} dias"},
    "n_meals": {"en": "{value} meals", "pt": "{value} refeições"},
    "n_kinds": {"en": "{value} kinds", "pt": "{value} tipos"},
}


def t(lang: str, key: str, **values: object) -> str:
    entry = _MESSAGES[key]
    return entry.get(lang, entry["en"]).format(**values)


def day_name(lang: str, index: int) -> str:
    return DAYS.get(lang, DAYS["en"])[index]


def word(lang: str, value: str) -> str:
    """A protein, tag or food-group word in the household's language."""
    return WORDS_PT.get(value, value) if lang == "pt" else value


def allergen(lang: str, value: str) -> str:
    return ALLERGENS_PT.get(value, value) if lang == "pt" else value


def equipment(lang: str, value: str) -> str:
    if lang == "pt":
        return EQUIPMENT_PT.get(value, value)
    return ("an " if value[0] in "aeiou" else "a ") + value


def pack(lang: str, label: str, count: int) -> str:
    if lang != "pt":
        return label if " of " in label or count == 1 else label + "s"
    one, many = PACKS_PT.get(label, (label, label))
    return one if count == 1 else many
