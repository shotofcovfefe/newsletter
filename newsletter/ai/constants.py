"""
Constants and configuration for AI models.
"""

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"

MODEL_CONFIGS = {
    PROVIDER_ANTHROPIC: {
        "model": "claude-3-7-sonnet-latest",
        "response_format": None,
        "web_search_details": {
            "model": "claude-3-7-sonnet-latest",
            "options": {
                "max_uses": 5,
                "user_location": {
                    "type": "approximate",
                    "city": "London",
                    "country": "GB"
                }
            }
        }
    },
    PROVIDER_OPENAI: {
        "model": "gpt-4o",
        "response_format": {"type": "json_object"},
        "web_search_details": {
            "model": "gpt-4o-mini-search-preview",
            "options": {
                "search_context_size": "medium",
                "user_location": {
                    "type": "approximate",
                    "approximate": {
                        "country": "GB",
                        # "city": "London",
                        # "region": "London",
                    }
                },
            }
        }
    },
}
