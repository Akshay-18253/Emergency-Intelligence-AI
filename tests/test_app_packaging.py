"""
Unit and integration tests for Milestone 8.4: System Packaging & Containerization.
================================================================================
Validates standard CLI script entrypoint, zero-dependency Dockerfile specification,
.dockerignore rules, EOC operator documentation completeness, and runtime health probes.
"""

from __future__ import annotations

import json
import re
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from emergency_intelligence.app.server import EmergencyAppServer, create_app, main


@pytest.fixture
def repo_root() -> Path:
    """Returns the absolute root directory of the repository."""
    return Path(__file__).resolve().parent.parent


def get_ephemeral_port() -> int:
    """Finds an available ephemeral TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestAppPackaging:
    """Test suite verifying CLI entrypoint, packaging configuration, and containerization."""

    def test_pyproject_scripts_entrypoint(self, repo_root: Path) -> None:
        """Verifies pyproject.toml defines emergency-intelligence-server entrypoint."""
        pyproject_path = repo_root / "pyproject.toml"
        assert pyproject_path.is_file(), "pyproject.toml must exist at repo root"

        content = pyproject_path.read_text(encoding="utf-8")
        assert "[project.scripts]" in content, "[project.scripts] table must be defined"
        assert 'emergency-intelligence-server = "emergency_intelligence.app.server:main"' in content, (
            "emergency-intelligence-server must map to emergency_intelligence.app.server:main"
        )

    def test_server_cli_dry_run_default(self) -> None:
        """Verifies CLI main function executes cleanly with --dry-run flag."""
        exit_code = main(["--dry-run"])
        assert exit_code == 0, "main with --dry-run must return 0"

    def test_server_cli_dry_run_custom_flags(self) -> None:
        """Verifies CLI main parses custom host, port, and logging flags."""
        port = get_ephemeral_port()
        exit_code = main(["--host", "127.0.0.1", "--port", str(port), "--log", "--dry-run"])
        assert exit_code == 0, "main with custom parameters and --dry-run must return 0"

    def test_dockerfile_zero_dependency_invariants(self, repo_root: Path) -> None:
        """Verifies Dockerfile adheres to zero external dependency rule and proper container hygiene."""
        dockerfile_path = repo_root / "Dockerfile"
        assert dockerfile_path.is_file(), "Dockerfile must exist at repo root"

        content = dockerfile_path.read_text(encoding="utf-8")

        # 1. Base image must be official python slim
        assert "FROM python:3.12-slim" in content or "FROM python:3" in content, (
            "Dockerfile should use a standard python-slim base image"
        )

        # 2. STRICT ZERO RUNTIME DEPENDENCIES: No pip install allowed in executable commands
        non_comment_lines = [
            line.strip() for line in content.splitlines() if not line.strip().startswith("#")
        ]
        assert not any("pip install" in line for line in non_comment_lines), (
            "Dockerfile must not contain 'pip install' steps (strictly standard library only)"
        )

        # 3. Security: non-root user creation
        assert "useradd" in content or "USER" in content, (
            "Dockerfile should configure a non-root system user"
        )

        # 4. Port exposure
        assert "EXPOSE 8080" in content, "Dockerfile must expose port 8080"

        # 5. Built-in healthcheck with urllib
        assert "HEALTHCHECK" in content, "Dockerfile must define a HEALTHCHECK"
        assert "urllib.request" in content, "Healthcheck must use stdlib urllib without curl/wget"
        assert "http://127.0.0.1:8080/api/health" in content

        # 6. Entrypoint execution
        assert "emergency_intelligence.app.server" in content

    def test_dockerignore_rules(self, repo_root: Path) -> None:
        """Verifies .dockerignore contains essential ignore directives."""
        dockerignore_path = repo_root / ".dockerignore"
        assert dockerignore_path.is_file(), ".dockerignore must exist at repo root"

        content = dockerignore_path.read_text(encoding="utf-8")
        assert ".git" in content
        assert ".venv" in content or "venv" in content
        assert "__pycache__" in content
        assert ".pytest_cache" in content

    def test_operator_manual_completeness(self, repo_root: Path) -> None:
        """Verifies docs/operator_manual.md covers all core operational domains."""
        manual_path = repo_root / "docs" / "operator_manual.md"
        assert manual_path.is_file(), "docs/operator_manual.md must exist"

        content = manual_path.read_text(encoding="utf-8")

        required_sections = [
            "Executive Overview",
            "System Architecture",
            "Launching the Embedded EOC Server",
            "Tactical Operations Dashboard Navigation",
            "Live CAD 911 Narrative Intake",
            "Web Audio Warning System",
            "Simulation Timeline & Playback Controller",
            "Dynamic Disaster Hazard Injection",
            "REST & Server-Sent Events",
            "Statutory Compliance & Non-Certification Notice",
        ]

        for section in required_sections:
            assert section.lower() in content.lower(), (
                f"Operator manual is missing required section: '{section}'"
            )

    def test_server_runtime_healthcheck(self) -> None:
        """Tests that a running server responds successfully to standard health probes."""
        port = get_ephemeral_port()
        server = create_app(host="127.0.0.1", port=port)
        server.start(blocking=False)
        time.sleep(0.05)

        try:
            health_url = f"http://127.0.0.1:{port}/api/health"
            req = urllib.request.Request(health_url, headers={"User-Agent": "EOC-HealthCheck/1.0"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                assert resp.status == 200
                res = json.loads(resp.read().decode("utf-8"))
                assert res.get("success") is True
                data = res.get("data", {})
                assert data.get("status") == "healthy"
                assert data.get("service") == "emergency-intelligence-ai"
                assert "version" in data
                assert "uptime_seconds" in data
        finally:
            server.stop()
