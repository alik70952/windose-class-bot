"""Secure password storage using the operating system credential backend."""

from __future__ import annotations

try:
    import keyring  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - CI without optional dependency.
    keyring = None  # type: ignore[assignment]

SERVICE_NAME = "windows-class-bot"


class CredentialStore:
    """Store and retrieve passwords without writing them to config.json."""

    def get_password(self, profile_id: str, username: str = "") -> str:
        """Return a saved password for the stable profile id, if available."""
        if not profile_id or keyring is None:
            return ""
        return keyring.get_password(SERVICE_NAME, self._account(profile_id)) or ""

    def save_password(self, profile_id: str, username: str, password: str) -> None:
        """Save a password in Windows Credential Manager or keyring backend."""
        if profile_id and password and keyring is not None:
            keyring.set_password(SERVICE_NAME, self._account(profile_id), password)

    def delete_password(self, profile_id: str) -> None:
        """Delete a saved profile password when it exists."""
        if not profile_id or keyring is None:
            return
        try:
            keyring.delete_password(SERVICE_NAME, self._account(profile_id))
        except keyring.errors.PasswordDeleteError:
            return

    @staticmethod
    def _account(profile_id: str) -> str:
        """Build a stable keyring account name that survives profile renames."""
        return f"windows-class-bot:{profile_id}"
