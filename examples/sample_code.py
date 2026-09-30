"""Sample code with intentional issues for PR review testing."""

import os
import sqlite3


# Hardcoded credentials (security issue)
DATABASE_PASSWORD = "admin123"
API_KEY = "sk-1234567890abcdef"


def get_user(username):
    """Get user from database - has SQL injection vulnerability."""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # SQL Injection vulnerability
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor.execute(query)
    return cursor.fetchone()


def process_items(items):
    """Process items - has N+1 query pattern."""
    results = []
    for item in items:
        # N+1 query pattern - fetching inside loop
        details = get_item_details(item.id)
        results.append(details)
    return results


def get_item_details(item_id):
    """Fetch item details."""
    conn = sqlite3.connect("items.db")
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM items WHERE id = {item_id}")
    return cursor.fetchone()


class UserManager:
    """User manager with multiple responsibilities (SRP violation)."""

    def __init__(self):
        self.db = sqlite3.connect("users.db")

    def create_user(self, username, password):
        # No password hashing
        cursor = self.db.cursor()
        cursor.execute(f"INSERT INTO users VALUES ('{username}', '{password}')")
        self.db.commit()

    def send_welcome_email(self, email):
        # This shouldn't be in UserManager
        print(f"Sending email to {email}")

    def generate_report(self):
        # This also shouldn't be here
        return "User report"

    def validate_password(self, password):
        # Weak password validation
        return len(password) > 3
