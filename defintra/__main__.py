"""
Defintra CLI execution entrypoint.
Allows running `python -m defintra ...` directly.
"""

from defintra.cli.main import app

if __name__ == "__main__":
    app()
