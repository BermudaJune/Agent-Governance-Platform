from __future__ import annotations

from agentgov.storage.db import connect, init_db


class SqliteRelationalStore:
    def __init__(self, database: str):
        self.database = database

    def init(self) -> None:
        init_db(self.database)

    def connect(self):
        return connect(self.database)
