"""Print the API description as JSON. The web app's types are generated from it.

python scripts/export_openapi.py > ../web/openapi.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Config  # noqa: E402
from app.main import create_app  # noqa: E402
from app.repo.memory import MemoryRepo  # noqa: E402

app = create_app(
    config=Config(push_enabled=False),
    repo=MemoryRepo(),
    verify_token=lambda token: {},
    use_default_ai=False,
)
print(json.dumps(app.openapi(), indent=2))
