from asgiref.sync import SyncToAsync
from channels.db import DatabaseSyncToAsync
from django.db import connections


class ClosingDatabaseSyncToAsync(DatabaseSyncToAsync):
    """DatabaseSyncToAsync that closes every worker-thread DB connection.

    Channels' default only closes *obsolete* connections (CONN_MAX_AGE based).
    Django's connection registry is thread-local, so under the test runner the
    worker threads' connections persist and prevent the test database from
    being dropped ("database is being accessed by other users"). Closing them
    unconditionally in the worker thread keeps the registry clean.
    """

    def thread_handler(self, loop, *args, **kwargs):
        try:
            return super().thread_handler(loop, *args, **kwargs)
        finally:
            for conn in connections.all(initialized_only=True):
                conn.close()


database_sync_to_async = ClosingDatabaseSyncToAsync


class ClosingSyncToAsync(SyncToAsync):
    """sync_to_async that also closes worker-thread DB connections."""

    def thread_handler(self, loop, *args, **kwargs):
        try:
            return super().thread_handler(loop, *args, **kwargs)
        finally:
            for conn in connections.all(initialized_only=True):
                conn.close()
