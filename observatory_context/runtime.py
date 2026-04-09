"""Runtime helpers for live and offline OpenViking workflows."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from observatory_context.client import OpenVikingObservatoryClient
from observatory_context.config import ObservatoryContextSettings
from observatory_context.service import ObservatoryContextService

if TYPE_CHECKING:
    from observatory_context.delivery import ContextDelivery
    from observatory_context.ingest.pipeline import IngestPipeline
    from observatory_context.registry.store import RegistryStore


def build_client(
    settings: ObservatoryContextSettings | None = None,
) -> OpenVikingObservatoryClient:
    """Construct the OpenViking client wrapper."""
    return OpenVikingObservatoryClient(settings or ObservatoryContextSettings())


def build_delivery(
    *,
    require_live: bool = True,
    with_extractor: bool = False,
) -> ContextDelivery:
    """Build a ContextDelivery instance with optional CBORG extractor.

    Parameters
    ----------
    require_live:
        If True, call ``client.health()`` and raise on failure.
    with_extractor:
        If True and a CBORG API key is configured, attach a
        CBORGExtractor to the delivery instance.
    """
    from observatory_context.delivery import ContextDelivery
    from observatory_context.extraction import CBORGExtractor

    settings = ObservatoryContextSettings()
    client = build_client(settings)
    if require_live:
        client.health()
    extractor = None
    if with_extractor and settings.cborg_api_key:
        extractor = CBORGExtractor(
            api_url=settings.cborg_api_url,
            model=settings.cborg_model,
            api_key=settings.cborg_api_key,
        )
    return ContextDelivery(client=client, extractor=extractor)


def build_service(
    repo_root: Path,
    offline: bool = False,
    require_live: bool = False,
    client: Any | None = None,
) -> ObservatoryContextService:
    """Build a service in offline or live-backed mode."""
    if offline:
        return ObservatoryContextService(repo_root=repo_root, client=None)

    resolved_client = client or build_client()
    if require_live and not resolved_client.health():
        raise RuntimeError("OpenViking server is not reachable")
    return ObservatoryContextService(repo_root=repo_root, client=resolved_client)


def build_registry_store(
    client: OpenVikingObservatoryClient | None = None,
) -> "RegistryStore":
    """Build a RegistryStore instance."""
    from observatory_context.registry.store import RegistryStore

    if client is None:
        settings = ObservatoryContextSettings()
        client = build_client(settings)
    return RegistryStore(client=client)


def build_ingest_pipeline(
    repo_root: Path | None = None,
    client: OpenVikingObservatoryClient | None = None,
) -> "IngestPipeline":
    """Build an IngestPipeline instance."""
    from observatory_context.ingest.pipeline import IngestPipeline

    if client is None:
        settings = ObservatoryContextSettings()
        client = build_client(settings)
    if repo_root is None:
        repo_root = Path.cwd()
    return IngestPipeline(client=client, repo_root=repo_root)
