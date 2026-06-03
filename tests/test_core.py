from __future__ import annotations

import time
import unittest
from datetime import timedelta
from unittest.mock import patch

from rq.cron import CronScheduler
from rq.utils import now

from rediscron.core import (
    CRON_JOBS_EVENTS_CHANNEL,
    CRON_JOBS_INDEX_KEY,
    CRON_JOBS_LAST_UPDATE_KEY,
    CRON_JOBS_LOCK_KEY,
    RedisCronJob,
    RedisCronScheduler,
)
from tests.conftest import FakeQueue, MemoryRedis, sample_task


class RedisCronJobTests(unittest.TestCase):
    def test_save_and_fetch_round_trip_executable_fields(self):
        redis = MemoryRedis()
        job = RedisCronJob(
            id="air-quality",
            queue_name="metrics",
            func=sample_task,
            args=(42,),
            kwargs={"marker": "pm25"},
            interval=30,
            result_ttl=10,
            meta={"source": "sensor"},
            connection=redis,
        )

        job.save()
        fetched = RedisCronJob.fetch("air-quality", redis)

        self.assertEqual(fetched.id, "air-quality")
        self.assertEqual(fetched.func, sample_task)
        self.assertEqual(fetched.func_name, "tests.conftest.sample_task")
        self.assertEqual(fetched.queue_name, "metrics")
        self.assertEqual(fetched.args, (42,))
        self.assertEqual(fetched.kwargs, {"marker": "pm25"})
        self.assertEqual(fetched.interval, 30)
        self.assertTrue(fetched.enabled)
        self.assertEqual(fetched.job_options["result_ttl"], 10)
        self.assertEqual(fetched.job_options["meta"], {"source": "sensor"})
        self.assertEqual(redis.hashes[job.key]["enabled"], 1)
        self.assertIn("air-quality", redis.zsets[CRON_JOBS_INDEX_KEY])

    def test_delete_removes_hash_and_index_entry(self):
        redis = MemoryRedis()
        job = RedisCronJob(
            id="stale",
            queue_name="default",
            func=sample_task,
            interval=60,
            connection=redis,
        )
        job.save()

        job.delete()

        self.assertEqual(redis.hgetall(job.key), {})
        self.assertNotIn("stale", redis.zsets[CRON_JOBS_INDEX_KEY])

    def test_disabled_job_is_persisted_but_not_indexed(self):
        redis = MemoryRedis()
        job = RedisCronJob(
            id="disabled",
            queue_name="default",
            func=sample_task,
            interval=60,
            connection=redis,
            enabled=False,
        )

        job.save()
        fetched = RedisCronJob.fetch("disabled", redis)

        self.assertFalse(fetched.enabled)
        self.assertEqual(redis.hashes[job.key]["enabled"], 0)
        self.assertNotIn("disabled", redis.zsets[CRON_JOBS_INDEX_KEY])

    def test_enable_and_disable_update_index_and_publish_events(self):
        redis = MemoryRedis()
        job = RedisCronJob(
            id="metric",
            queue_name="default",
            func=sample_task,
            interval=60,
            connection=redis,
        )
        job.save()

        job.disable()

        self.assertFalse(RedisCronJob.fetch("metric", redis).enabled)
        self.assertNotIn("metric", redis.zsets[CRON_JOBS_INDEX_KEY])
        self.assertEqual(redis.events[-1][0], CRON_JOBS_EVENTS_CHANNEL)
        self.assertIn('"event":"disabled"', redis.events[-1][1])

        job.enable()

        self.assertTrue(RedisCronJob.fetch("metric", redis).enabled)
        self.assertIn("metric", redis.zsets[CRON_JOBS_INDEX_KEY])
        self.assertIn('"event":"enabled"', redis.events[-1][1])


class RedisCronSchedulerTests(unittest.TestCase):
    def setUp(self):
        FakeQueue.calls = []

    def test_register_same_id_edits_existing_job(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        scheduler.register(sample_task, "default", id="metric", args=(1,), interval=60)
        first = RedisCronJob.fetch("metric", redis)
        scheduler.register(
            sample_task, "critical", id="metric", args=(2,), interval=120
        )

        edited = RedisCronJob.fetch("metric", redis)
        self.assertEqual(edited.created_at, first.created_at)
        self.assertEqual(edited.queue_name, "critical")
        self.assertEqual(edited.args, (2,))
        self.assertEqual(edited.interval, 120)
        self.assertEqual(list(redis.zsets[CRON_JOBS_INDEX_KEY]), ["metric"])

    def test_register_preserves_disabled_existing_job_by_default(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        scheduler.register(
            sample_task, "default", id="metric", args=(1,), interval=60, enabled=False
        )

        scheduler.register(
            sample_task, "critical", id="metric", args=(2,), interval=120
        )

        edited = RedisCronJob.fetch("metric", redis)
        self.assertFalse(edited.enabled)
        self.assertNotIn("metric", redis.zsets[CRON_JOBS_INDEX_KEY])

    def test_register_can_enable_existing_disabled_job(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        scheduler.register(
            sample_task, "default", id="metric", args=(1,), interval=60, enabled=False
        )

        scheduler.register(
            sample_task, "critical", id="metric", args=(2,), interval=120, enabled=True
        )

        edited = RedisCronJob.fetch("metric", redis)
        self.assertTrue(edited.enabled)
        self.assertIn("metric", redis.zsets[CRON_JOBS_INDEX_KEY])

    def test_enqueue_jobs_uses_lock_and_updates_next_schedule(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        job = scheduler.register(
            sample_task, "default", id="metric", args=(1,), interval=60
        )
        job.next_enqueue_time = now() - timedelta(seconds=1)
        job.save()
        self.assertIsNotNone(scheduler._acquire_lock())

        import rediscron.core as redis_cron

        original_queue = redis_cron.Queue
        redis_cron.Queue = FakeQueue
        try:
            enqueued = scheduler.enqueue_jobs()
        finally:
            redis_cron.Queue = original_queue

        self.assertEqual([job.id for job in enqueued], ["metric"])
        self.assertEqual(FakeQueue.calls[0][0], "default")
        fetched = RedisCronJob.fetch("metric", redis)
        self.assertIsNotNone(fetched.latest_enqueue_time)
        self.assertGreater(redis.zsets[CRON_JOBS_INDEX_KEY]["metric"], time.time())
        self.assertIn(CRON_JOBS_LOCK_KEY, redis.strings)

    def test_enqueue_jobs_skips_disabled_jobs(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        job = scheduler.register(
            sample_task, "default", id="metric", args=(1,), interval=60
        )
        job.next_enqueue_time = now() - timedelta(seconds=1)
        job.disable()
        redis.zadd(CRON_JOBS_INDEX_KEY, {"metric": time.time() - 1})
        self.assertIsNotNone(scheduler._acquire_lock())

        self.assertEqual(scheduler.enqueue_jobs(), [])
        self.assertEqual(FakeQueue.calls, [])
        self.assertNotIn("metric", redis.zsets[CRON_JOBS_INDEX_KEY])

    def test_enqueue_without_owned_scheduler_lock_does_not_enqueue(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        job = scheduler.register(
            sample_task, "default", id="metric", args=(1,), interval=60
        )
        job.next_enqueue_time = now() - timedelta(seconds=1)
        job.save()
        redis.set(CRON_JOBS_LOCK_KEY, "other-owner")

        self.assertEqual(scheduler.enqueue_jobs(), [])
        self.assertEqual(FakeQueue.calls, [])

    def test_register_birth_acquires_lifetime_lock(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)

        with patch.object(CronScheduler, "register_birth") as register_birth:
            scheduler.register_birth()

        register_birth.assert_called_once_with()
        self.assertEqual(redis.get(CRON_JOBS_LOCK_KEY), scheduler._lock_token)

    def test_register_birth_fails_when_another_scheduler_owns_lock(self):
        redis = MemoryRedis()
        redis.set(CRON_JOBS_LOCK_KEY, "other-owner")
        scheduler = RedisCronScheduler(redis)

        with patch.object(CronScheduler, "register_birth") as register_birth:
            with self.assertRaises(RuntimeError):
                scheduler.register_birth()

        register_birth.assert_not_called()

    def test_register_death_releases_owned_lifetime_lock(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        token = scheduler._acquire_lock()
        self.assertIsNotNone(token)

        with patch.object(CronScheduler, "register_death") as register_death:
            scheduler.register_death()

        register_death.assert_called_once_with(None)
        self.assertNotIn(CRON_JOBS_LOCK_KEY, redis.strings)

    def test_release_lock_does_not_delete_another_owner(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        redis.set(CRON_JOBS_LOCK_KEY, "other-owner")

        self.assertFalse(scheduler._release_lock("mine"))
        self.assertEqual(redis.get(CRON_JOBS_LOCK_KEY), "other-owner")

    def test_calculate_sleep_interval_reads_sorted_set(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        redis.zadd(CRON_JOBS_INDEX_KEY, {"metric": time.time() + 5})

        sleep = scheduler.calculate_sleep_interval()

        self.assertGreater(sleep, 0)
        self.assertLessEqual(sleep, 5)

    def test_update_marker_changes_when_job_saved(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        self.assertIsNone(scheduler.last_seen_update)

        RedisCronJob(
            id="metric",
            queue_name="default",
            func=sample_task,
            interval=60,
            connection=redis,
        ).save()

        self.assertTrue(scheduler._refresh_update_marker())
        self.assertIsNotNone(redis.get(CRON_JOBS_LAST_UPDATE_KEY))

    def test_get_jobs_returns_enabled_jobs_only(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        scheduler.register(sample_task, "default", id="enabled", interval=60)
        scheduler.register(
            sample_task, "default", id="disabled", interval=60, enabled=False
        )

        jobs = scheduler.get_jobs()

        self.assertEqual([job.id for job in jobs], ["enabled"])

    def test_get_all_jobs_returns_enabled_and_disabled_jobs(self):
        redis = MemoryRedis()
        scheduler = RedisCronScheduler(redis)
        scheduler.register(sample_task, "default", id="enabled", interval=60)
        scheduler.register(
            sample_task, "default", id="disabled", interval=60, enabled=False
        )

        jobs = scheduler.get_all_jobs()

        self.assertEqual([job.id for job in jobs], ["disabled", "enabled"])


if __name__ == "__main__":
    unittest.main()
