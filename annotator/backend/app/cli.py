"""Admin CLI (no HTTP, no email — this deployment is offline).

    python -m app.cli create-admin [--username NAME] [--password PW]
    python -m app.cli reset-password USERNAME [--password PW]
"""
import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select, update

from app.core.errors import AppError
from app.core.security import check_password_policy, hash_password
from app.db.session import dispose_engine, get_sessionmaker
from app.db.types import utcnow
from app.models import RefreshSession, Role, User
from app.services.audit import audit


def _ask_password(given: str | None) -> str:
    if given:
        return given
    pw = getpass.getpass("Password: ")
    if pw != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match")
    return pw


async def create_admin(username: str, password: str) -> None:
    username = username.strip().lower()
    check_password_policy(password, username)
    async with get_sessionmaker()() as db:
        if await db.scalar(select(User.id).where(User.username == username)):
            sys.exit(f"User '{username}' already exists")
        db.add(User(username=username, role=Role.admin.value, password_hash=await hash_password(password),
                    active=True, must_change_password=False))
        audit(db, "cli", "users.create_admin", "user", None, {"username": username})
        await db.commit()
    print(f"Admin '{username}' created")


async def reset_password(username: str, password: str) -> None:
    username = username.strip().lower()
    check_password_policy(password, username)
    async with get_sessionmaker()() as db:
        user = await db.scalar(select(User).where(User.username == username))
        if user is None:
            sys.exit(f"No such user '{username}'")
        user.password_hash = await hash_password(password)
        user.active = True
        user.must_change_password = True
        await db.execute(update(RefreshSession).where(RefreshSession.user_id == user.id,
                                                      RefreshSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
        audit(db, "cli", "users.reset_password", "user", user.id)
        await db.commit()
    print(f"Password for '{username}' reset; they must change it at next login")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("create-admin")
    a.add_argument("--username")
    a.add_argument("--password")
    r = sub.add_parser("reset-password")
    r.add_argument("username")
    r.add_argument("--password")
    args = p.parse_args(argv)

    async def run():
        try:
            if args.cmd == "create-admin":
                await create_admin(args.username or input("Username: "), _ask_password(args.password))
            else:
                await reset_password(args.username, _ask_password(args.password))
        except AppError as e:
            sys.exit(f"error: {e.message}")
        finally:
            await dispose_engine()

    asyncio.run(run())


if __name__ == "__main__":
    main()
