"""One process owns a local SQLite workspace; OS releases the lock on crash."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path


@contextmanager
def workspace_lock(database_path):
    path = Path(str(Path(database_path).resolve()) + '.lock')
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Một backend khác đang dùng không gian dữ liệu này. Dừng phiên đó trước khi mở lại; chưa đổi trạng thái job hoặc ví.') from None
        os.ftruncate(descriptor, 0)
        os.write(descriptor, str(os.getpid()).encode('ascii'))
        yield
    finally:
        # Closing the descriptor releases the lock even during startup failure.
        # Keep the file: unlinking it would let two processes lock two inodes.
        os.close(descriptor)
