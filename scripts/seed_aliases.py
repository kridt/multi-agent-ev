"""Script to seed alias data into the database."""

import asyncio
import sys
from pathlib import Path

# Ensure project root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.session import get_session
from entity_resolution.seed_data import seed_aliases


async def main() -> None:
    async with get_session() as session:
        count = await seed_aliases(session)
        print(f"Seeded {count} aliases")


if __name__ == "__main__":
    asyncio.run(main())
