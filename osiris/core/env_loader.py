"""Unified environment loading for Osiris."""

import os
from pathlib import Path

from dotenv import load_dotenv


def load_env(dotenv_paths: list[str] | None = None) -> list[str]:
    """Load environment variables from .env files.

    Loads process env (no-op for already exported vars) + optionally .env files.

    Default search order:
    1. $OSIRIS_HOME/.env (if OSIRIS_HOME environment variable is set)
    2. CWD (.env)
    3. Project root where osiris.py lives (.env)
    4. testing_env/.env if CWD is testing_env/

    Args:
        dotenv_paths: Optional list of specific .env paths to load.
                     If provided, only these are loaded (no default search).

    Returns:
        List of .env file paths that were successfully loaded.

    Note:
        - Idempotent (safe to call multiple times)
        - Already exported env vars take precedence over .env files
        - Empty strings in env vars are treated as unset
        - OSIRIS_HOME takes highest priority to ensure env vars are loaded from
          the project directory regardless of where the command is run from
    """
    loaded_paths = []

    if dotenv_paths:
        # Use explicit paths if provided
        for path in dotenv_paths:
            if Path(path).exists():
                load_dotenv(path, override=False)  # Don't override existing env vars
                loaded_paths.append(path)
    else:
        # Default search order
        cwd = Path.cwd()

        # 1. $OSIRIS_HOME/.env (highest priority if set)
        osiris_home = os.environ.get("OSIRIS_HOME")
        if osiris_home:
            osiris_home_env = Path(osiris_home) / ".env"
            if osiris_home_env.exists():
                load_dotenv(osiris_home_env, override=False)
                loaded_paths.append(str(osiris_home_env))

        # 2. CWD/.env
        cwd_env = cwd / ".env"
        if cwd_env.exists() and str(cwd_env) not in loaded_paths:
            load_dotenv(cwd_env, override=False)
            loaded_paths.append(str(cwd_env))

        # 3. Project root (where osiris.py lives)
        # Walk up to find osiris.py
        current = cwd
        while current != current.parent:
            if (current / "osiris.py").exists():
                project_env = current / ".env"
                if project_env.exists() and str(project_env) not in loaded_paths:
                    load_dotenv(project_env, override=False)
                    loaded_paths.append(str(project_env))
                break
            current = current.parent

        # 4. testing_env/.env if CWD is testing_env/
        if cwd.name == "testing_env":
            testing_env = cwd / ".env"
            if testing_env.exists() and str(testing_env) not in loaded_paths:
                load_dotenv(testing_env, override=False)
                loaded_paths.append(str(testing_env))

    return loaded_paths
