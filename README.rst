############
rq-rediscron
############

``rq-rediscron`` provides Redis-backed subclasses for RQ cron scheduling:

- ``RedisCronJob``
- ``RedisCronScheduler``

Cron job definitions are stored in Redis hashes and indexed in a sorted set by
next enqueue time. This lets scheduler processes pick up job creates, edits, and
deletes at runtime without restart.

Only one ``RedisCronScheduler`` process runs at a time. The scheduler acquires
``rq:cron_jobs:lock`` during ``register_birth()``, extends that lock on heartbeat,
and releases it during ``register_death()``. A second scheduler can start after
the lock TTL expires, which provides failover without duplicate enqueue loops.

Usage
=====

.. code-block:: python

    from redis import Redis
    from rediscron import RedisCronScheduler


    def rebuild_metric(metric_id: str) -> None:
        ...


    connection = Redis.from_url("redis://localhost:6379/0")
    scheduler = RedisCronScheduler(connection)
    scheduler.register(
        rebuild_metric,
        queue_name="metrics",
        id="metric:pm25",
        args=("pm25",),
        interval=300,
    )
    scheduler.start()

Redis keys
==========

Keys used by this package:

- ``rq:cron_job:{id}`` stores one cron job hash.
- ``rq:cron_jobs`` indexes job ids by next enqueue timestamp.
- ``rq:cron_jobs:lock`` allows one live scheduler process at a time.
- ``rq:cron_jobs:last_update`` records runtime changes.
- ``rq:cron_jobs:events`` publishes create, update, and delete events.

Why?
====

The original `cron <https://python-rq.org/docs/cron/>`__ `implementation
<https://github.com/rq/rq/blob/master/rq/cron.py>`__ in `RQ
<https://python-rq.org/>`__ is holding all the cron jobs locally as a list
inside the instance of the scheduler. Because of this design choice, as soon as
the scheduler is started, the list of scheduled jobs cannot be easily modified.

In some cases, we want to be able to add/edit/delete scheduled jobs on the fly
and for the scheduler to acknowledge those events accordingly. This is what
lead the design choices for this package.

Inspired by `redisbeat <https://github.com/sibson/redbeat>`__, a celery
scheduler using redis to store metadata. See `Hello RedBeat: A New Celery Beat
Scheduler <https://www.heroku.com/blog/redbeat-celery-beat-scheduler/>`__ for
mor info.
