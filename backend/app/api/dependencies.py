"""Shared FastAPI dependencies for the backend service."""

from __future__ import annotations

from ..services.api_data_service import DatasetService


_dataset_service = DatasetService()


def get_dataset_service() -> DatasetService:
    """Return the application-level cached dataset service."""

    return _dataset_service
