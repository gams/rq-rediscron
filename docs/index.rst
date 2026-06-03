.. rq-rediscron documentation master file, created by
   sphinx-quickstart on Fri May 29 00:11:16 2026.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

##############################################
rq-rediscron - Redis-backed RQ cron scheduling
##############################################

.. include:: ../README.rst
   :start-line: 4
   :end-line: 52

Code
====

.. automodule:: rediscron.core
   :members:
   :member-order: bysource

CLI
===

To see what scheduled jobs are currently registered (enabled or disabled), just
type ``rqrcron info``:

.. code-block:: shell

   $ rqrcron info
   visits  */1 * * * *  enabled   2026-06-03T05:40:00.000000Z  analytics    
   vacuum  every 10s    enabled   2026-06-03T05:39:35.962178Z  maintenance  
   2 scheduled jobs total

   Updated: 2026-06-03 12:39:35.320659

To see the scheduled jobs grouped by queue, just use the ``-R`` (or
``--by-queue``) flag:

.. code-block:: shell

   $ rqrcron info -R
   analytics:
     visits  */1 * * * *  enabled   2026-06-03T05:41:00.000000Z

   maintenance:
     vacuum  every 10s  enabled   2026-06-03T05:40:16.790579Z

   2 queues, 2 scheduled jobs total

   Updated: 2026-06-03 12:40:14.200368

To watch scheduled jobs, you can specify a poll interval using the ``-i`` (or
``--interval``) flag:

.. code-block:: shell

   $ rqrcron info -i 1

Why?
====

.. include:: ../README.rst
   :start-line: 71
