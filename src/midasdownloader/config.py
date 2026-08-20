"""Configuration management for MidasDownloader admit card downloader."""

from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

# Automatically load .env file from project root or current working directory
load_dotenv(override=False)


def get_default_output_dir() -> Path:
    """Generates a timestamped output directory path: out/YYYY-MM-DD_HH-MM-SS."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return Path(f"out/{timestamp}")


def extract_user_agent_from_ci_session(cookie_str: str) -> Optional[str]:
    """Auto-extracts the User-Agent embedded in CodeIgniter's ci_session cookie."""
    try:
        decoded = urllib.parse.unquote(cookie_str)
        match = re.search(r's:10:\"user_agent\";s:\d+:\"([^\"]+)\"', decoded)
        if match:
            return match.group(1).replace("+", " ")
    except Exception:
        pass
    return None


@dataclass
class Settings:
    """Application settings loaded from environment or CLI arguments."""

    url_template: str = ""
    cookie_name: str = field(
        default_factory=lambda: os.getenv("COOKIE_NAME", "ci_session")
    )
    cookie_value: str = field(
        default_factory=lambda: os.getenv("COOKIE_VALUE", os.getenv("POSSID", os.getenv("ci_session", "")))
    )
    output_dir: Path = field(
        default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "")) if os.getenv("OUTPUT_DIR") else get_default_output_dir()
    )
    request_delay: float = field(
        default_factory=lambda: float(os.getenv("REQUEST_DELAY", "0.4"))
    )
    timeout: float = field(
        default_factory=lambda: float(os.getenv("REQUEST_TIMEOUT", "20.0"))
    )
    user_agent: str = field(
        default_factory=lambda: os.getenv(
            "USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        )
    )

    def get_cookie_header(self) -> str:
        """Returns the raw Cookie header string safely without double encoding."""
        val = self.cookie_value.strip()
        if not val:
            return ""
        if "=" in val:
            return val
        return f"{self.cookie_name}={val}"

    def get_effective_user_agent(self) -> str:
        """Returns the matched User-Agent (from ci_session cookie or default)."""
        extracted = extract_user_agent_from_ci_session(self.cookie_value)
        if extracted:
            return extracted
        return self.user_agent

    def get_headers(self) -> Dict[str, str]:
        """Returns standard browser headers for HTTP requests."""
        headers = {
            "User-Agent": self.get_effective_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/pdf",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": self.url_template.rsplit("/", 1)[0] if "/" in self.url_template else "https://portal.university.example.edu/",
        }
        cookie_header = self.get_cookie_header()
        if cookie_header:
            headers["Cookie"] = cookie_header
        return headers
