"""CLI helper to create an initial admin user: python -m app.scripts.create_admin"""

import argparse
import asyncio

from app.crud.user import create_user, get_user_by_email
from app.db.session import AsyncSessionLocal
from app.models.user import UserRole


async def _run(email: str, password: str, full_name: str, role: UserRole) -> None:
    async with AsyncSessionLocal() as db:
        existing = await get_user_by_email(db, email)
        if existing:
            print(f"User {email} already exists (role={existing.role.value}).")
            return
        user = await create_user(
            db,
            email=email,
            password=password,
            full_name=full_name,
            role=role,
        )
        print(f"Created user {user.email} (id={user.id}, role={user.role.value}).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an HRMS AI user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default="Admin")
    parser.add_argument("--role", default="admin", choices=[r.value for r in UserRole])
    args = parser.parse_args()
    asyncio.run(_run(args.email, args.password, args.name, UserRole(args.role)))


if __name__ == "__main__":
    main()
