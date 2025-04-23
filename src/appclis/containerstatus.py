import asyncio

import typer
import uvloop
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from docker import DockerClient
from docker.errors import DockerException
from dotenv import load_dotenv
from loguru import logger

from libcoolifydockerstatuses.containerstatus import ContainerStatusTracker
from libcoolifydockerstatuses.webhooknotifier import WebhookNotifier

uvloop.install()
load_dotenv()
app = typer.Typer(pretty_exceptions_enable=False)


async def print_container_status_report(tracker: ContainerStatusTracker) -> None:
    """Print a status report of all monitored containers asynchronously

    Args:
        tracker: Container status tracker instance
    """
    containers = await tracker.get_monitored_containers()

    if not containers:
        logger.info("No containers with monitoring enabled found")
        return

    logger.info(f"Status report for {len(containers)} monitored containers:")

    # Create tasks for getting status of each container
    status_tasks = []
    for container in containers:
        status_tasks.append(tracker.get_container_status(container))

    # Wait for all status checks to complete
    statuses = await asyncio.gather(*status_tasks)

    # Print status report
    for container, status in zip(containers, statuses):
        logger.info(f"  - {container.name} ({container.id[:12]}): {status.name}")


async def shutdown(scheduler: AsyncIOScheduler, notifier: WebhookNotifier) -> None:
    """Shutdown the application gracefully

    Args:
        scheduler: The scheduler to shut down
        notifier: Webhook notifier to close
    """
    logger.info("Shutting down...")
    scheduler.shutdown(wait=False)

    await notifier.close()


async def run(
    monitor_interval_in_seconds: int,
    docker_socket: str,
    status_change_webhook_url: str,
    coolify_monitor_label: str,
    coolify_project_name: str,
    coolify_environment_name: str,
) -> None:
    """
    Main function to run the Docker container deployment monitor

    Returns:
        None
    """
    logger.info(f"Monitoring Interval: {monitor_interval_in_seconds} seconds")

    try:
        docker_client = DockerClient(base_url=docker_socket)
        docker_client.ping()
    except DockerException as e:
        logger.error(f"Failed to connect to Docker daemon: {e}")
        return

    # The docker container status tracker
    tracker = ContainerStatusTracker(
        docker_client=docker_client,
        monitor_label=coolify_monitor_label,
        coolify_project_name=coolify_project_name,
        coolify_environment_name=coolify_environment_name,
    )

    # The webhook notifier
    notifier = WebhookNotifier(
        webhook_url=status_change_webhook_url,
        docker_client=docker_client,
        webhook_timeout=30,
    )

    # Print initial status report
    await print_container_status_report(tracker=tracker)

    # Set up scheduler for periodic status checks
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        tracker.check_container_statuses,
        trigger=IntervalTrigger(seconds=monitor_interval_in_seconds),
        id="check_container_statuses",
        name="Check container statuses",
        replace_existing=True,
    )

    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started, monitoring containers...")

    # Run forever
    try:
        await asyncio.Future()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Received exit signal, shutting down...")
        await notifier.close()
        scheduler.shutdown(wait=False)


@app.command()
def main(
    monitor_interval_in_seconds: int = typer.Option(
        5,
        help="Monitor interval in seconds",
        allow_dash=True,
        envvar="MONITOR_INTERVAL_IN_SECONDS",
    ),
    docker_socket: str = typer.Option(
        ..., help="Docker socket", allow_dash=True, envvar="DOCKER_SOCKET"
    ),
    status_change_webhook_url: str = typer.Option(
        ...,
        help="Webhook URL for status changes",
        allow_dash=True,
        envvar="STATUS_CHANGE_WEBHOOK_URL",
    ),
    coolify_monitor_label: str = typer.Option(
        ...,
        help="Label to identify containers to monitor",
        allow_dash=True,
        envvar="COOLIFY_MONITOR_LABEL",
    ),
    coolify_project_name: str = typer.Option(
        ...,
        help="Project name to identify containers to monitor",
        allow_dash=True,
        envvar="COOLIFY_PROJECT_NAME",
    ),
    coolify_environment_name: str = typer.Option(
        ...,
        help="Environment name to identify containers to monitor",
        allow_dash=True,
        envvar="COOLIFY_ENVIRONMENT_NAME",
    ),
):
    """
    Main entry point for the Docker container deployment monitor.

    Returns:
        None
    """
    logger.info("Starting Docker container deployment monitor")

    asyncio.run(
        run(
            monitor_interval_in_seconds=monitor_interval_in_seconds,
            docker_socket=docker_socket,
            status_change_webhook_url=status_change_webhook_url,
            coolify_monitor_label=coolify_monitor_label,
            coolify_project_name=coolify_project_name,
            coolify_environment_name=coolify_environment_name,
        )
    )


if __name__ == "__main__":
    app()
