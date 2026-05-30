import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.database.config import Base, engine
from backend.database.migrations import run_migrations


def main() -> None:
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    print("Migrations applied successfully.")


if __name__ == "__main__":
    main()
