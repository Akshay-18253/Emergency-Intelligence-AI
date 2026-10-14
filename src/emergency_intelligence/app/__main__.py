"""CLI entry point for running the web application directly: python -m emergency_intelligence.app"""

from __future__ import annotations

from emergency_intelligence.app.server import main

if __name__ == "__main__":
    main()
