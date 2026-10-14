"""Prints the API's OpenAPI schema, from which the frontend's types are generated:
`uv run python -m nlab.api.openapi > ../frontend/openapi.json`, then `npm run gen` in frontend/."""

import json

from nlab.api.app import create_app
from nlab.api.settings import Settings
from nlab.llm import OpenAICompatibleProvider

if __name__ == "__main__":
    settings = Settings(_env_file=None, production=False, secret_key="openapi-only")  # offline schema export
    app = create_app(settings, providers={}, llm=(OpenAICompatibleProvider(), None))  # no model: nothing is called
    print(json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False))
