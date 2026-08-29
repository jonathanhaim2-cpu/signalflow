#!/usr/bin/env python3
"""Grant Pro to a user by email. Does not charge.

Usage:
    python scripts/grant_pro.py email@x.com
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import AsyncSessionLocal, init_db  # noqa: E402
from app.services.plans import grant_pro  # noqa: E402


async def main(email: str) -> int:
    await init_db()
    async with AsyncSessionLocal() as db:
        user = await grant_pro(db, email)
        if not user:
            print(f"User not found: {email}")
            return 1
        print(f"Granted Pro to {user.email} (tier={user.tier})")
        return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("Usage: python scripts/grant_pro.py email@x.com")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
