"""All external traffic and Redis are replaced by isolated fixtures."""
import os

os.environ["ROOMBEACON_ENV_FILE"] = "/dev/null"
pytest_plugins = ["tests.fixtures.meeting_rooms"]
