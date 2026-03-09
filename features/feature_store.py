"""Feature vector persistence layer."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.base import new_uuid
from db.models.predictions import FeatureVector


class FeatureStore:
    """Save and retrieve feature vectors from the database."""

    @staticmethod
    async def save_features(
        session: AsyncSession,
        match_id: str,
        entity_type: str,
        entity_id: str,
        features: dict,
        version: str = "v1",
    ) -> str:
        """Save a feature vector to the DB.

        Args:
            session: Async SQLAlchemy session.
            match_id: The match this feature vector belongs to.
            entity_type: 'team' or 'player'.
            entity_id: The team or player ID.
            features: The feature dict to store (will be JSON-serialised).
            version: Feature schema version.

        Returns:
            The generated feature_vector ID.
        """
        fv_id = new_uuid()
        fv = FeatureVector(
            id=fv_id,
            match_id=match_id,
            entity_type=entity_type,
            entity_id=entity_id,
            feature_version=version,
            features=json.dumps(features),
            computed_at=datetime.now(timezone.utc),
        )
        session.add(fv)
        await session.flush()
        return fv_id

    @staticmethod
    async def get_features(
        session: AsyncSession,
        match_id: str,
        entity_id: str,
        version: str = "v1",
    ) -> dict | None:
        """Retrieve a feature vector from the DB.

        Returns the parsed feature dict, or None if not found.
        """
        stmt = (
            select(FeatureVector)
            .where(FeatureVector.match_id == match_id)
            .where(FeatureVector.entity_id == entity_id)
            .where(FeatureVector.feature_version == version)
            .order_by(FeatureVector.computed_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return json.loads(row.features)

    @staticmethod
    async def get_features_for_match(
        session: AsyncSession,
        match_id: str,
        version: str = "v1",
    ) -> list[dict]:
        """Get all feature vectors for a match.

        Returns a list of dicts, each containing the entity metadata and parsed features.
        """
        stmt = (
            select(FeatureVector)
            .where(FeatureVector.match_id == match_id)
            .where(FeatureVector.feature_version == version)
            .order_by(FeatureVector.computed_at.desc())
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": row.id,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "features": json.loads(row.features),
                "computed_at": row.computed_at.isoformat(),
            }
            for row in rows
        ]
