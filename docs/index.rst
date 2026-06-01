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
   bar */1 * * * *  enabled   blah  
   foo every 10s    enabled   blah  
   2 scheduled jobs total

   Updated: 2026-06-02 00:29:50.050084

To see the scheduled jobs grouped by queue, just use the ``-R`` (or
``--by-queue``) flag:

.. code-block:: shell

   $ rqrcron info -R
   blah:
     bar  */1 * * * *  enabled 
     foo  every 10s    enabled 

   1 queues, 2 scheduled jobs total

   Updated: 2026-06-02 00:29:45.197421

Why?
====

.. include:: ../README.rst
   :start-line: 71
