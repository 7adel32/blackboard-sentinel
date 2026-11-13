"""Application version and release metadata for Blackboard Sentinel."""

APP_NAME = "BlackboardSentinel"
APP_DISPLAY_NAME = "Blackboard Sentinel"
APP_VERSION = "1.1.13"
GITHUB_REPO = "7adel32/blackboard-sentinel"
GITHUB_TOKEN = ""

try:
    import _release_meta  # type: ignore[import-not-found]
except ImportError:
    _release_meta = None
else:
    APP_VERSION = getattr(_release_meta, "APP_VERSION", APP_VERSION) or APP_VERSION
    GITHUB_REPO = getattr(_release_meta, "GITHUB_REPO", GITHUB_REPO) or GITHUB_REPO
    GITHUB_TOKEN = getattr(_release_meta, "GITHUB_TOKEN", GITHUB_TOKEN) or GITHUB_TOKEN
