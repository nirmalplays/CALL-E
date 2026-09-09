"""Minimal async document store.

Implements the small slice of the Motor/PyMongo async API this package uses
(``get_collection`` -> ``find_one`` / ``insert_one`` / ``update_one`` / ``find_all``)
so the readback flow runs with no database installed.

Swap in a real Motor database and everything else works unchanged — that is the
whole point of taking ``db`` as a parameter rather than importing a client.

    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(uri)["medai"]        # production
    db = InMemoryDB()                            # demo / tests
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional


class _Result:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class InMemoryCollection:
    """An async, dict-matching collection backed by a list."""

    def __init__(self, name: str):
        self.name = name
        self._docs: List[Dict[str, Any]] = []

    @staticmethod
    def _matches(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
        return all(doc.get(k) == v for k, v in query.items())

    async def insert_one(self, doc: Dict[str, Any]) -> _Result:
        self._docs.append(copy.deepcopy(doc))
        return _Result(inserted_id=len(self._docs) - 1)

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for d in self._docs:
            if self._matches(d, query):
                return d
        return None

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> _Result:
        doc = await self.find_one(query)
        if doc is None:
            return _Result(modified_count=0)
        doc.update(update.get("$set", {}))
        return _Result(modified_count=1)

    async def find_all(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Not part of the Motor API — convenience for the demo dashboard."""
        if not query:
            return list(self._docs)
        return [d for d in self._docs if self._matches(d, query)]

    async def count(self) -> int:
        return len(self._docs)


class InMemoryDB:
    """Stand-in for a Motor database handle."""

    def __init__(self):
        self._collections: Dict[str, InMemoryCollection] = {}

    def get_collection(self, name: str) -> InMemoryCollection:
        if name not in self._collections:
            self._collections[name] = InMemoryCollection(name)
        return self._collections[name]

    def collection_names(self) -> List[str]:
        return sorted(self._collections)
