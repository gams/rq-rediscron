from __future__ import annotations

import sys
import time
from collections import defaultdict
from datetime import datetime

import click
from redis.exceptions import ConnectionError
from rq.cli.helpers import pass_cli_config
from rq.utils import utcformat

from .core import RedisCronJob, RedisCronScheduler


def _schedule(job: RedisCronJob) -> str:
    if job.cron:
        return job.cron
    return f"every {job.interval}s"


def _state(job: RedisCronJob) -> str:
    return "enabled" if job.enabled else "disabled"


def _next_run(job: RedisCronJob) -> str:
    next_enqueue_time = job.next_enqueue_time
    if next_enqueue_time is None and job.interval and not job.latest_enqueue_time:
        return "now"
    if next_enqueue_time is None:
        next_enqueue_time = job.get_next_enqueue_time()
    if next_enqueue_time == datetime.max:
        return "-"
    return utcformat(next_enqueue_time)


def _job_sort_key(job: RedisCronJob) -> tuple[str, str, str]:
    return (job.queue_name, _schedule(job), job.id)


def _load_jobs(connection, queues: tuple[str, ...]) -> list[RedisCronJob]:
    scheduler = RedisCronScheduler(connection)
    jobs = scheduler.get_all_jobs()
    if queues:
        queue_names = set(queues)
        jobs = [job for job in jobs if job.queue_name in queue_names]
    return sorted(jobs, key=_job_sort_key)


def _show_jobs(jobs: list[RedisCronJob]) -> None:
    if not jobs:
        click.echo("No scheduled jobs")
        return

    max_queue = max(len(job.queue_name) for job in jobs)
    max_schedule = max(len(_schedule(job)) for job in jobs)
    max_next_run = max(len(_next_run(job)) for job in jobs)
    for job in jobs:
        click.echo(
            f"{job.id}  "
            f"{_schedule(job):<{max_schedule}}  "
            f"{_state(job):<8}  "
            f"{_next_run(job):<{max_next_run}}  "
            f"{job.queue_name:<{max_queue}}  "
        )
    click.echo(f"{len(jobs)} scheduled jobs total")


def _show_jobs_by_queue(jobs: list[RedisCronJob]) -> None:
    if not jobs:
        click.echo("No scheduled jobs")
        return

    grouped: dict[str, list[RedisCronJob]] = defaultdict(list)
    for job in jobs:
        grouped[job.queue_name].append(job)

    for queue_name in sorted(grouped):
        queue_jobs = sorted(grouped[queue_name], key=_job_sort_key)
        max_schedule = max(len(_schedule(job)) for job in queue_jobs)
        max_next_run = max(len(_next_run(job)) for job in queue_jobs)
        click.echo(f"{queue_name}:")
        for job in queue_jobs:
            click.echo(
                f"  {job.id}  "
                f"{_schedule(job):<{max_schedule}}  "
                f"{_state(job):<8}  "
                f"{_next_run(job):<{max_next_run}}"
            )
        click.echo("")

    click.echo(f"{len(grouped)} queues, {len(jobs)} scheduled jobs total")


def _show_info(jobs: list[RedisCronJob], by_queue: bool) -> None:
    if by_queue:
        _show_jobs_by_queue(jobs)
    else:
        _show_jobs(jobs)
    click.echo("")
    click.echo(f"Updated: {datetime.now()}")


def _refresh(
    interval: float | None, connection, queues: tuple[str, ...], by_queue: bool
) -> None:
    while True:
        jobs = _load_jobs(connection, queues)
        if interval:
            click.clear()
        _show_info(jobs, by_queue)
        if interval:
            time.sleep(interval)
        else:
            break


@click.group()
def main() -> None:
    """rq-rediscron command line tools."""


@main.command()
@click.option("--interval", "-i", type=float, help="Updates stats every N seconds.")
@click.option("--by-queue", "-R", is_flag=True, help="List scheduled jobs by queue.")
@click.argument("queues", nargs=-1)
@pass_cli_config
def info(
    cli_config,
    interval: float | None,
    by_queue: bool,
    queues: tuple[str, ...],
    **options,
) -> None:
    """List scheduled Redis cron jobs."""
    try:
        _refresh(interval, cli_config.connection, queues, by_queue)
    except ConnectionError as exc:
        click.echo(exc)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo()
        sys.exit(0)


if __name__ == "__main__":
    main()
