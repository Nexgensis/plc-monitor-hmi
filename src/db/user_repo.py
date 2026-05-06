"""
user_repo.py — Universal PLC Monitor
Manages the 'users' table for authentication and access control.
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, Any

from .database import Database

logger = logging.getLogger(__name__)


class UserRepository:
    """
    Repository for user management.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Finds a user by their login name."""
        return self.db.fetchone(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        )

    def authenticate(self, username: str, password_hash: str) -> Optional[Dict[str, Any]]:
        """
        Validates credentials. 
        Note: In a production app, password_hash would be compared using a 
        secure library like bcrypt or argon2.
        """
        user = self.db.fetchone(
            "SELECT * FROM users WHERE UPPER(username) = UPPER(?) AND password_hash = ?",
            (username.strip(), password_hash)
        )
        if user:
            self.db.execute(
                "UPDATE users SET last_login = datetime('now','utc') WHERE id = ?",
                (user["id"],)
            )
            return dict(user)
        return None

    def create_user(self, username: str, password_hash: str, role: str) -> int:
        """Adds a new user to the system."""
        if role not in ("ADMIN", "OPERATOR", "SUPERVISOR"):
            raise ValueError(f"Invalid role: {role}")
            
        query = "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)"
        cursor = self.db.execute(query, (username.strip(), password_hash, role))
        return cursor.lastrowid

    def get_all_users(self) -> list[Dict[str, Any]]:
        """Returns list of all users."""
        return self.db.fetchall("SELECT id, username, role, created_at, last_login FROM users")

    def update_user(self, user_id: int, **kwargs) -> bool:
        """Updates user details."""
        if "username" in kwargs:
            # Check for name collision
            existing = self.get_user_by_username(kwargs["username"])
            if existing and existing["id"] != user_id:
                raise ValueError("Username already exists.")

        fields = [f"{k} = ?" for k in kwargs.keys()]
        params = list(kwargs.values())
        params.append(user_id)
        
        query = f"UPDATE users SET {', '.join(fields)} WHERE id = ?"
        self.db.execute(query, tuple(params))
        return True

    def delete_user(self, user_id: int) -> bool:
        """Removes a user. Cannot delete the last admin."""
        user = self.db.fetchone("SELECT role FROM users WHERE id = ?", (user_id,))
        if user and user["role"] == "ADMIN":
            admin_count = self.db.fetchone("SELECT COUNT(*) as count FROM users WHERE role = 'ADMIN'")
            if admin_count["count"] <= 1:
                raise ValueError("Cannot delete the last administrator.")
                
        self.db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return True
