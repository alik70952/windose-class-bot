"""Secure password storage using the operating system credential backend."""

from __future__ import annotations

import keyring

SERVICE_NAME = "WindowsClassBot"


class CredentialStore:
    """Store and retrieve passwords without writing them to config.json."""

    def get_password(self, profile_name: str, username: str) -> str:
        """Return a saved password for the profile and username, if available."""
        if not profile_name or not username:
            return ""
        return keyring.get_password(SERVICE_NAME, self._account(profile_name, username)) or ""

    def save_password(self, profile_name: str, username: str, password: str) -> None:
        """Save a password in Windows Credential Manager or keyring backend."""
        if profile_name and username and password:
            keyring.set_password(SERVICE_NAME, self._account(profile_name, username), password)

    @staticmethod
    def _account(profile_name: str, username: str) -> str:
        """Build a stable keyring account name for a profile."""
        return f"{profile_name}:{username}"
