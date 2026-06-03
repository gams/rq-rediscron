from __future__ import annotations

import unittest
from unittest.mock import PropertyMock, patch

from click.testing import CliRunner
from rq.utils import utcformat

import rediscron.cli as rediscron_cli
from rediscron.cli import main as cli_main
from rediscron.core import RedisCronScheduler
from tests.conftest import MemoryRedis, sample_task


class CliTests(unittest.TestCase):
    def test_info_lists_enabled_and_disabled_jobs(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        cleanup = scheduler.register(
            sample_task, "default", id="cleanup", cron="*/5 * * * *"
        )
        hourly_metrics = scheduler.register(
            sample_task,
            "metrics",
            id="hourly-metrics",
            cron="0 * * * *",
            enabled=False,
        )

        runner = CliRunner()
        with patch(
            "rq.cli.helpers.CliConfig.connection",
            new_callable=PropertyMock,
            return_value=redis,
        ):
            result = runner.invoke(cli_main, ["info"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("default", result.output)
        self.assertIn("*/5 * * * *", result.output)
        self.assertIn("enabled", result.output)
        self.assertIn("cleanup", result.output)
        self.assertIn(utcformat(cleanup.next_enqueue_time), result.output)
        self.assertIn("metrics", result.output)
        self.assertIn("0 * * * *", result.output)
        self.assertIn("disabled", result.output)
        self.assertIn("hourly-metrics", result.output)
        self.assertIn(utcformat(hourly_metrics.next_enqueue_time), result.output)
        self.assertIn("2 scheduled jobs total", result.output)
        self.assertIn("Updated:", result.output)

    def test_info_by_queue_groups_scheduled_jobs(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        scheduler.register(sample_task, "default", id="fast", interval=60)
        scheduler.register(sample_task, "default", id="slow", interval=120)
        scheduler.register(sample_task, "metrics", id="hourly", cron="0 * * * *")

        runner = CliRunner()
        with patch(
            "rq.cli.helpers.CliConfig.connection",
            new_callable=PropertyMock,
            return_value=redis,
        ):
            result = runner.invoke(cli_main, ["info", "-R"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("default:", result.output)
        self.assertIn("every 60s", result.output)
        self.assertIn("now", result.output)
        self.assertIn("every 120s", result.output)
        self.assertIn("metrics:", result.output)
        self.assertIn("0 * * * *", result.output)
        self.assertIn("2 queues, 3 scheduled jobs total", result.output)

    def test_info_filters_by_queue_name(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        scheduler.register(sample_task, "default", id="cleanup", interval=60)
        scheduler.register(sample_task, "metrics", id="hourly", interval=120)

        runner = CliRunner()
        with patch(
            "rq.cli.helpers.CliConfig.connection",
            new_callable=PropertyMock,
            return_value=redis,
        ):
            result = runner.invoke(cli_main, ["info", "metrics"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertNotIn("cleanup", result.output)
        self.assertIn("metrics", result.output)
        self.assertIn("hourly", result.output)
        self.assertIn("1 scheduled jobs total", result.output)

    def test_interval_refresh_loads_jobs_before_clearing_screen(self):
        events = []

        def load_jobs(connection, queues):
            events.append("load")
            return []

        def clear():
            events.append("clear")

        def show_info(jobs, by_queue):
            events.append("show")

        def sleep(interval):
            events.append("sleep")
            raise KeyboardInterrupt

        with (
            patch.object(rediscron_cli, "_load_jobs", load_jobs),
            patch.object(rediscron_cli.click, "clear", clear),
            patch.object(rediscron_cli, "_show_info", show_info),
            patch.object(rediscron_cli.time, "sleep", sleep),
        ):
            with self.assertRaises(KeyboardInterrupt):
                rediscron_cli._refresh(1, object(), (), False)

        self.assertEqual(events, ["load", "clear", "show", "sleep"])


if __name__ == "__main__":
    unittest.main()
