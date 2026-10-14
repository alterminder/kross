from nlab.api.llm_settings import llm_config_from_env


def test_no_key_means_no_model():
    assert llm_config_from_env({}) is None


def test_the_default_role_and_per_role_overrides():
    config = llm_config_from_env(
        {
            "LLM_API_KEY": "main-key",
            "LLM_BASE_URL": "https://main.example/v1",
            "LLM_MODEL": "main-model",
            "CLASSIFIER_MODEL": "deepseek-flash",
            "CLASSIFIER_REASONING_EFFORT": "low",
            "EVALUATOR_THINKING": "off",
            "AVATAR_BASE_URL": "https://fast.example/v1",
            "AVATAR_API_KEY": "fast-key",
            "AVATAR_CLOSING_EFFORT": "low",
            "AVATAR_FIRST_WORD_SECONDS": "12",
        }
    )
    assert config is not None
    assert config.default.model == "main-model" and config.default.base_url == "https://main.example/v1"
    classifier = config.for_role("classifier")
    assert classifier.model == "deepseek-flash" and classifier.reasoning_effort == "low"
    assert classifier.base_url == "https://main.example/v1"  # inherited
    assert config.for_role("grant") == classifier  # the grant check follows the classifier, as in the hackathon
    assert config.for_role("evaluator").thinking is False
    counterpart = config.for_role("counterpart")
    assert counterpart.base_url == "https://fast.example/v1" and counterpart.api_key.get_secret_value() == "fast-key"
    assert counterpart.closing_reasoning_effort == "low" and counterpart.first_word_seconds == 12
    assert config.for_role("debrief") == config.default
    converter = config.for_role("converter")
    assert converter.timeout_seconds == 300 and converter.max_retries == 0  # every paid retry passes admission


def test_an_empty_key_means_no_model():
    assert llm_config_from_env({"LLM_API_KEY": ""}) is None  # .env.example ships LLM_API_KEY= empty


def test_a_role_base_url_without_a_role_key_is_ignored():
    """Hackathon behaviour: <ROLE>_BASE_URL applies only with <ROLE>_API_KEY, so the main key never goes elsewhere."""
    config = llm_config_from_env(
        {
            "LLM_API_KEY": "main-key",
            "LLM_BASE_URL": "https://api.deepseek.com",
            "AVATAR_BASE_URL": "https://other.example/v1",  # leftover, its AVATAR_API_KEY commented out
        }
    )
    assert config is not None
    counterpart = config.for_role("counterpart")
    assert counterpart.base_url == "https://api.deepseek.com"
    assert counterpart.api_key.get_secret_value() == "main-key"
