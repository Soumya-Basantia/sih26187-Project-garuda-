"""
One-time setup script: creates the bootstrap admin user (since the
/api/auth/register endpoint requires an existing admin — chicken/egg
problem for the very first account).

Run once:  python seed.py
"""

import asyncio
import getpass
from app.database import users_col, ensure_indexes
from app.auth import hash_password


async def main():
    await ensure_indexes()
    existing = await users_col.find_one({"role": "ADMIN"})
    if existing:
        print(f"An admin user already exists: {existing['username']}. Nothing to do.")
        return

    print("No admin user found. Let's create the first one.")
    username = input("Admin username [admin]: ").strip() or "admin"
    password = getpass.getpass("Admin password: ")
    if len(password) < 6:
        print("Password too short (min 6 characters). Aborting.")
        return

    await users_col.insert_one({
        "username": username,
        "password_hash": hash_password(password),
        "role": "ADMIN",
    })
    print(f"Admin user '{username}' created. You can now log in via /api/auth/login.")


if __name__ == "__main__":
    asyncio.run(main())
