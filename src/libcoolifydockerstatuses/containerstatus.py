import asyncio
from typing import Any, Callable, Coroutine, Dict, List, Set

from docker import DockerClient
from docker.errors import APIError, NotFound
from docker.models.containers import Container
from loguru import logger

from libcoolifydockerstatuses.constants import ContainerStatus


class ContainerStatusTracker:
    """Tracks the status of Docker containers asynchronously"""

    def __init__(self, docker_client: DockerClient, monitor_label: str) -> None:
        """Initialize the container status tracker

        Args:
            docker_client: Docker client instance
            monitor_label: Label used to filter containers for monitoring
        """
        self.docker_client = docker_client
        self.monitor_label = monitor_label

        self.container_statuses: Dict[str, ContainerStatus] = {}
        self.status_change_callbacks: List[
            Callable[[str, ContainerStatus, ContainerStatus], Coroutine[Any, Any, None]]
        ] = []

    def register_status_change_callback(
        self,
        callback: Callable[
            [str, ContainerStatus, ContainerStatus], Coroutine[Any, Any, None]
        ],
    ) -> None:
        """Register a callback for container status changes

        Args:
            callback: Async function to call when a container status changes
        """
        self.status_change_callbacks.append(callback)

    async def get_monitored_containers(self) -> List[Container]:
        """Get all containers with the monitoring label asynchronously

        Returns:
            List of containers that should be monitored
        """
        try:
            # Use run_in_executor to make the Docker API call non-blocking
            loop = asyncio.get_running_loop()
            containers = await loop.run_in_executor(
                None,
                lambda: self.docker_client.containers.list(
                    all=True, filters={"label": f"{self.monitor_label}=true"}
                ),
            )
            return containers
        except APIError as e:
            logger.error(f"Error getting containers: {e}")
            return []

    async def get_container_status(self, container: Container) -> ContainerStatus:
        """Get the current status of a container asynchronously

        Args:
            container: Docker container object

        Returns:
            Current status of the container
        """
        try:
            # Use run_in_executor to make the Docker API call non-blocking
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, container.reload)

            status_str = container.status.lower()

            # Map Docker status string to our enum
            if status_str == "created":
                return ContainerStatus.CREATED
            elif status_str == "running":
                return ContainerStatus.RUNNING
            elif status_str == "restarting":
                return ContainerStatus.RESTARTING
            elif status_str == "exited":
                return ContainerStatus.EXITED
            elif status_str == "paused":
                return ContainerStatus.PAUSED
            elif status_str == "dead":
                return ContainerStatus.DEAD
            elif status_str == "removing":
                return ContainerStatus.REMOVING
            else:
                return ContainerStatus.UNKNOWN

        except NotFound:
            # Container was removed
            return ContainerStatus.UNKNOWN
        except APIError as e:
            logger.error(f"Error getting container status: {e}")
            return ContainerStatus.UNKNOWN

    async def check_container_statuses(self) -> None:
        """Check the status of all monitored containers and report changes asynchronously"""
        containers = await self.get_monitored_containers()

        # Track current container IDs to detect removed containers
        current_container_ids: Set[str] = set()

        # Create tasks for status checks
        status_check_tasks = []
        for container in containers:
            container_id = container.id
            current_container_ids.add(container_id)
            status_check_tasks.append(self._check_container_status(container))

        # Wait for all status checks to complete
        await asyncio.gather(*status_check_tasks)

        # Check for containers that were removed
        removal_tasks = []
        for container_id in list(self.container_statuses.keys()):
            if container_id not in current_container_ids:
                previous_status = self.container_statuses[container_id]
                del self.container_statuses[container_id]

                logger.info(f"Container {container_id[:12]} was removed")

                for callback in self.status_change_callbacks:
                    removal_tasks.append(
                        callback(container_id, previous_status, ContainerStatus.UNKNOWN)
                    )

        # Wait for all removal notifications to complete
        if removal_tasks:
            await asyncio.gather(*removal_tasks)

    async def _check_container_status(self, container: Container) -> None:
        """Check status of a single container and trigger callbacks if changed

        Args:
            container: Docker container to check
        """
        container_id = container.id
        current_status = await self.get_container_status(container)
        previous_status = self.container_statuses.get(
            container_id, ContainerStatus.UNKNOWN
        )

        # Update status in our tracking dict
        self.container_statuses[container_id] = current_status

        # If status changed, notify callbacks
        if current_status != previous_status:
            logger.info(
                f"Container {container.name} ({container_id[:12]}) status changed: {previous_status.name} -> {current_status.name}"
            )

            callback_tasks = []
            for callback in self.status_change_callbacks:
                callback_tasks.append(
                    callback(container_id, previous_status, current_status)
                )

            # Run all callbacks concurrently
            if callback_tasks:
                await asyncio.gather(*callback_tasks)
