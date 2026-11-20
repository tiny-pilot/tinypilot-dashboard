"""Assistant configuration from environment and SQLite."""

import os
from dataclasses import dataclass
from typing import Optional

from app.db import get_db

_ALLOWED_CONFIG_KEYS = frozenset({'instructions', 'max_steps', 'timeout'})


@dataclass
class AssistantConfig:
    """Runtime configuration for the assistant."""

    api_key: str
    model: str = 'gpt-4o'
    base_url: str = 'https://api.openai.com/v1'
    instructions: str = ''
    max_steps: int = 20
    timeout: float = 120.0

    @classmethod
    def from_env(cls) -> Optional['AssistantConfig']:
        """Load config from environment. Returns None if not configured."""
        api_key = os.environ.get('ASSISTANT_API_KEY', '').strip()
        if not api_key:
            return None
        return cls(
            api_key=api_key,
            model=os.environ.get('ASSISTANT_MODEL', 'gpt-4o').strip(),
            base_url=os.environ.get('ASSISTANT_BASE_URL',
                                    'https://api.openai.com/v1').strip(),
        )


def get_config() -> Optional[AssistantConfig]:
    """Get merged config from env + SQLite. Returns None if not enabled."""
    config = AssistantConfig.from_env()
    if config is None:
        return None
    # Overlay SQLite settings.
    db = get_db()
    for row in db.execute('SELECT key, value FROM assistant_config').fetchall():
        key, value = row['key'], row['value']
        if key == 'instructions':
            config.instructions = value or ''
        elif key == 'max_steps':
            try:
                config.max_steps = int(value)
            except (TypeError, ValueError):
                pass
        elif key == 'timeout':
            try:
                config.timeout = float(value)
            except (TypeError, ValueError):
                pass
    return config


def set_config(updates: dict) -> None:
    """Update SQLite config keys."""
    db = get_db()
    for key, value in updates.items():
        if key not in _ALLOWED_CONFIG_KEYS:
            continue
        db.execute(
            'INSERT OR REPLACE INTO assistant_config (key, value) VALUES (?, ?)',
            (key, str(value)),
        )
    db.commit()


def get_config_dict() -> dict:
    """Return current config as dict (for API response)."""
    config = get_config()
    if config is None:
        return {'enabled': False}
    return {
        'enabled': True,
        'model': config.model,
        'base_url': config.base_url,
        'instructions': config.instructions,
        'max_steps': config.max_steps,
        'timeout': config.timeout,
    }
