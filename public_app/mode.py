"""Public is the safe default; the original research router requires an explicit opt-in."""
import os


def app_mode() -> str:
    """Never infer access to the full research environment from the presence of local files."""
    return 'full' if os.environ.get('APP_MODE', '').strip().lower() == 'full' else 'public'
