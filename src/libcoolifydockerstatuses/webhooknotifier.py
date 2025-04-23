import asyncio
from datetime import datetime
from typing import Dict

import httpx
import pytz
from docker import DockerClient
from docker.errors import NotFound
from loguru import logger
from pydantic import BaseModel, Field

from libcoolifydockerstatuses.constants import ContainerStatus


class ContainerInfo(BaseModel):
    id: str
    name: str | None = "unknown"
    image: str | None = "unknown"
    labels: Dict[str, str] | None = Field(default_factory=dict)
    created: datetime | None = None
    error: str | None = None


class WebhookPayload(BaseModel):
    event_type: str = "container_status_change"
    timestamp: str
    container: ContainerInfo
    previous_status: str
    current_status: str


class WebhookNotifier:
    """Sends container status changes to a webhook asynchronously"""

    def __init__(
        self, webhook_url: str, docker_client: DockerClient, webhook_timeout: int = 20
    ) -> None:
        """Initialize the webhook notifier

        Args:
            webhook_url: URL to send webhook notifications to
            docker_client: Docker client instance
        """
        self.webhook_url = webhook_url
        self.docker_client = docker_client
        self.http_client = httpx.AsyncClient(timeout=webhook_timeout)

    async def notify_status_change(
        self,
        container_id: str,
        previous_status: ContainerStatus,
        current_status: ContainerStatus,
    ) -> None:
        """Send a notification about a container status change asynchronously

        Args:
            container_id: ID of the container
            previous_status: Previous container status
            current_status: Current container status
        """
        if not self.webhook_url:
            logger.debug("No webhook URL configured, skipping notification")
            return

        try:
            # Get container details asynchronously
            container_info = await self._get_container_info(container_id)

            # Prepare payload
            payload = {
                "event_type": "container_status_change",
                "timestamp": datetime.now(tz=pytz.UTC).isoformat(),
                "container": container_info,
                "previous_status": previous_status.name,
                "current_status": current_status.name,
            }

            # Send webhook asynchronously
            response = await self.http_client.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code >= 400:
                logger.error(
                    f"Webhook request failed with status {response.status_code}: {response.text}"
                )
            else:
                logger.debug("Webhook notification sent successfully")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error sending webhook notification: {e}")
        except Exception as e:
            logger.error(f"Error sending webhook notification: {e}")

    async def _get_container_info(self, container_id: str) -> ContainerInfo:
        """Get detailed information about a container asynchronously

        Args:
            container_id: ID of the container

        Returns:
            Dictionary with container details
        """
        try:
            # Use run_in_executor to make the Docker API call non-blocking
            loop = asyncio.get_running_loop()
            container = await loop.run_in_executor(
                None, lambda: self.docker_client.containers.get(container_id)
            )

            # Extract container information
            return ContainerInfo(
                **{
                    "id": container_id,
                    "name": container.name,
                    "image": container.image.tags[0]
                    if container.image.tags
                    else str(container.image.id),
                    "labels": container.labels,
                    "created": container.attrs.get("Created", ""),
                }
            )
        except NotFound:
            # Container was removed
            return ContainerInfo(
                **{
                    "id": container_id,
                    "name": "unknown",
                    "image": "unknown",
                    "labels": {},
                    "created": "",
                }
            )
        except Exception as e:
            logger.error(f"Error getting container info: {e}")
            return ContainerInfo(**{"id": container_id, "error": str(e)})

    async def close(self) -> None:
        """Close the HTTP client"""
        await self.http_client.aclose()
