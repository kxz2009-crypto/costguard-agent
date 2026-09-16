"""Hermes cumulative metadata -> durable incremental claims (local only).

Default first observation is a baseline, not historical ingestion. Source rows
are grouped by session/model/billing provider without reading task/URL fields.
A scan and its checkpoint/outbox changes are one transaction. Delivery is
at-least-once; the existing server's source_event_id contract deduplicates it.
"""
from __future__ import annotations

import argparse
import fcntl
import stat
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3

from costguard_split.identity.device_uid import validate_device_uid
from costguard_split.schemas.usage import UsageEventClaim

FIELDS = ('request_count', 'input_tokens', 'output_tokens', 'cached_input_tokens',
          'cache_write_tokens', 'reasoning_tokens')
SQL = '''SELECT session_id, model, billing_provider,
SUM(api_call_count), SUM(input_tokens), SUM(output_tokens),
SUM(cache_read_tokens), SUM(cache_write_tokens), SUM(reasoning_tokens),
MIN(first_seen), MAX(last_seen)
FROM session_model_usage GROUP BY session_id, model, billing_provider'''


class SourceRegression(ValueError):
    """Source counters/time regressed; retain checkpoints and require investigation."""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def _stamp(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('source timestamp must be finite epoch seconds')
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


class HermesIncremental:
    def __init__(self, source_db, state_dir, device_uid):
        if not validate_device_uid(device_uid):
            raise ValueError('invalid device UID')
        self.source = Path(source_db).expanduser().resolve(strict=True)
        self.state = Path(state_dir).expanduser()
        if self.state.is_symlink():
            raise ValueError('state directory must not be a symlink')
        self.state = self.state.resolve()
        if self.state == self.source.parent or self.state.is_relative_to(self.source.parent):
            raise ValueError('checkpoint state must be outside the Hermes source directory')
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.state, 0o700)
        self.path = self.state / 'checkpoint.sqlite3'
        if self.path.is_symlink() or (self.path.exists() and self.path.samefile(self.source)):
            raise ValueError('unsafe checkpoint path')
        self.device_uid = device_uid
        source_fd = os.open(self.source, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            source_stat = os.fstat(source_fd)
        finally:
            os.close(source_fd)
        if not stat.S_ISREG(source_stat.st_mode):
            raise ValueError('Hermes source must be a regular file')
        self._source_identity = (source_stat.st_dev, source_stat.st_ino)
        # Bind a state directory to exactly one source file and device.
        self.binding = hashlib.sha256(_json([str(self.source),
                            *self._source_identity, device_uid]).encode()).hexdigest()
        ds = self.state.stat()
        self._directory_identity = (ds.st_dev, ds.st_ino)
        self._file_identity = None
        self._anchor_fd = None
        self._directory_anchor = None
        self._closed = False
        with self._open() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS streams (key TEXT PRIMARY KEY,counters TEXT NOT NULL,seen REAL NOT NULL,first REAL NOT NULL,revision INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', ('schema_version','2'))
            if db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] != '2':
                raise ValueError('unsupported checkpoint schema')
            db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', ('binding', self.binding))
            db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', ('salt', secrets.token_hex(32)))
            if db.execute("SELECT value FROM meta WHERE key='binding'").fetchone()[0] != self.binding:
                raise ValueError('state belongs to a different source file or device')

    def close(self):
        self._closed = True
        for name in ('_anchor_fd','_directory_anchor'):
            fd = getattr(self,name,None)
            if fd is not None:
                fcntl.flock(fd,fcntl.LOCK_UN)
                os.close(fd)
                setattr(self,name,None)

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()

    def __del__(self):
        try:
            self.close()
        except (OSError,AttributeError,TypeError):
            pass

    @contextmanager
    def _open(self):
        # Revalidate on every operation; hold descriptors/lock until SQL closes.
        if self._closed:
            raise ValueError('collector is closed')
        directory = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fd = None
        db = None
        try:
            ds = os.fstat(directory)
            if ((ds.st_dev,ds.st_ino) != self._directory_identity or
                    ds.st_uid != os.geteuid() or stat.S_IMODE(ds.st_mode) != 0o700):
                raise ValueError('checkpoint directory identity/ownership changed')
            fd = os.open('checkpoint.sqlite3', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            fs = os.fstat(fd)
            identity = (fs.st_dev,fs.st_ino)
            source = self.source.stat()
            if (not stat.S_ISREG(fs.st_mode) or fs.st_uid != os.geteuid() or
                    fs.st_nlink != 1 or identity == (source.st_dev,source.st_ino) or
                    (self._file_identity is not None and identity != self._file_identity)):
                raise ValueError('checkpoint file identity/ownership/alias changed')
            if self._anchor_fd is None:
                # Pin inodes for this object's lifetime, including between scans.
                self._anchor_fd = os.dup(fd)
                self._directory_anchor = os.dup(directory)
            os.fchmod(fd,0o600)
            fcntl.flock(fd,fcntl.LOCK_EX)
            self._file_identity = identity
            def check_path():
                ds_now = os.stat(self.state,follow_symlinks=False)
                fs_now = os.stat('checkpoint.sqlite3',dir_fd=directory,follow_symlinks=False)
                if ((ds_now.st_dev,ds_now.st_ino) != self._directory_identity or
                        (fs_now.st_dev,fs_now.st_ino) != identity or
                        not stat.S_ISREG(fs_now.st_mode) or fs_now.st_nlink != 1):
                    raise ValueError('checkpoint path replaced')
            check_path()
            db = sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=30)
            check_path()
            with db:
                yield db
                check_path()
        finally:
            if db is not None:
                db.close()
            if fd is not None:
                fcntl.flock(fd,fcntl.LOCK_UN)
                os.close(fd)
            os.close(directory)

    @contextmanager
    def _open_source(self):
        """Open read-only and prove SQLite opened the collector's bound inode."""
        source_fd = os.open(self.source, os.O_RDONLY | os.O_NOFOLLOW)
        src = None
        try:
            source_stat = os.fstat(source_fd)
            identity = (source_stat.st_dev, source_stat.st_ino)
            if (not stat.S_ISREG(source_stat.st_mode) or
                    identity != self._source_identity):
                raise ValueError('source file was replaced; do not reuse this state')
            descriptor_path = next((Path(root) / str(source_fd)
                                    for root in ('/proc/self/fd', '/dev/fd')
                                    if os.path.isdir(root)), None)
            if descriptor_path is None:
                raise OSError('descriptor-backed SQLite open is unavailable')
            try:
                # SQLite opens the pinned descriptor path, never the independently
                # mutable source pathname. mode=ro preserves the source boundary.
                src = sqlite3.connect(descriptor_path.as_uri() + '?mode=ro',
                                      uri=True, timeout=3)
            except sqlite3.Error:
                try:
                    current = self.source.stat()
                except OSError:
                    current = None
                if (current is None or
                        (current.st_dev, current.st_ino) != identity):
                    raise ValueError('source file was replaced; do not reuse this state')
                raise
            current = self.source.stat()
            if (current.st_dev, current.st_ino) != identity:
                raise ValueError('opened source does not match bound source identity')
            src.execute('PRAGMA query_only=ON')
            yield src
        finally:
            if src is not None:
                src.close()
            os.close(source_fd)

    def resume_after_investigation(self):
        """Explicit operator acknowledgment; never rewrites source/checkpoints.

        If the underlying regression remains, the next scan halts again.
        """
        with self._open() as db:
            db.execute("DELETE FROM meta WHERE key='halted'")

    def scan(self, *, include_history=False):
        """Queue deltas; a decreasing counter/time aborts the whole scan.

        include_history applies only to the first scan. Future new streams
        are included in full; already baselined history is never backfilled.
        """
        failure = None
        result = None
        with self._open() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT value FROM meta WHERE key='halted'").fetchone():
                raise SourceRegression('collector halted; explicit investigation/resume required')
            db.execute('SAVEPOINT scan_changes')
            try:
                result = self._scan_locked(db,include_history)
                db.execute('RELEASE scan_changes')
            except SourceRegression as exc:
                db.execute('ROLLBACK TO scan_changes')
                db.execute('RELEASE scan_changes')
                db.execute("INSERT OR REPLACE INTO meta VALUES ('halted',?)",(str(exc),))
                failure = exc
        if failure is not None:
            raise failure
        return result

    def _scan_locked(self, db, include_history):
        queued = baseline = unchanged = empty = 0
        cold_start = db.execute("SELECT value FROM meta WHERE key='initialized'").fetchone() is None
        salt = bytes.fromhex(db.execute("SELECT value FROM meta WHERE key='salt'").fetchone()[0])
        with self._open_source() as src:
            rows = src.execute(SQL).fetchall()
        for sid, model, provider, *values in rows:
            counters, first, seen = values[:6], values[6], values[7]
            if any(type(n) is not int or n < 0 for n in counters):
                raise ValueError('invalid cumulative source counter')
            if not isinstance(sid,str) or not sid or not isinstance(model,str) or not model.strip():
                raise ValueError('invalid source identity')
            original_provider = provider
            if provider is not None and not isinstance(provider,str):
                raise ValueError('invalid billing provider')
            key = hmac.new(salt,_json([sid,model,original_provider]).encode(),hashlib.sha256).hexdigest()
            old = db.execute('SELECT counters,seen,revision,first FROM streams WHERE key=?',(key,)).fetchone()
            if not any(counters) and first is None and seen is None:
                if old:
                    raise SourceRegression('observed stream reset to empty')
                empty += 1
                continue
            _stamp(first); _stamp(seen)
            if first > seen:
                raise ValueError('invalid source time interval')
            provider = provider or 'unknown'
            if not provider.strip():
                raise ValueError('invalid billing provider')
            if old:
                previous, previous_seen, revision = json.loads(old[0]), old[1], old[2]
                if first != old[3] or seen < previous_seen or any(n < p for n,p in zip(counters,previous)):
                    raise SourceRegression('source counter/time regression; checkpoint unchanged')
                delta = [n-p for n,p in zip(counters,previous)]
                start = previous_seen
            else:
                delta = counters if include_history or not cold_start else [0]*6
                revision = 0
                start = first
                baseline += 1
            if any(delta):
                revision += 1
                event_id = 'hermes-'+key+'-'+str(revision)
                claim = UsageEventClaim(device_uid=self.device_uid,provider=provider,model=model,
                    source_event_id=event_id,session_ref='hermes-'+key,
                    started_at=_stamp(start),ended_at=_stamp(seen),
                    collector_version='hermes-cumulative-v1',source_type='connector',
                    **dict(zip(FIELDS,delta)))
                db.execute('INSERT INTO outbox VALUES (?,?)',(event_id,claim.model_dump_json()))
                queued += 1
            else:
                unchanged += 1
            db.execute('INSERT OR REPLACE INTO streams VALUES (?,?,?,?,?)',(key,_json(counters),seen,first,revision))
        db.execute("INSERT OR REPLACE INTO meta VALUES ('initialized','1')")
        return {'streams':len(rows),'new_baselines':baseline,'queued':queued,'unchanged':unchanged,'empty_unobserved':empty}

    def pending(self):
        with self._open() as db:
            rows = db.execute('SELECT payload FROM outbox ORDER BY rowid').fetchall()
        return [UsageEventClaim.model_validate_json(row[0]) for row in rows]

    def deliver(self, send):
        """send(claim) returns an HTTP-like response. Ack only matching success.

        Transport exceptions, non-success and mismatched receipts retain the
        durable outbox. The caller supplies transport and owns authentication.
        No network, profile, credential or target configuration lives here.
        """
        acknowledged = 0
        for claim in self.pending():
            with self._open() as db:
                if db.execute("SELECT value FROM meta WHERE key='halted'").fetchone():
                    raise SourceRegression('collector halted; delivery paused')
            response = send(claim)
            if response.status_code not in (200,201):
                raise RuntimeError('delivery rejected; pending event retained')
            receipt = response.json()
            expected = claim.provider.strip().lower()+':'+claim.source_event_id
            if (receipt.get('source_event_id') != expected or
                    receipt.get('device_uid') != claim.device_uid or not receipt.get('id') or
                    receipt.get('model') != claim.model or
                    any(receipt.get(k) != getattr(claim,k) for k in FIELDS)):
                raise RuntimeError('delivery receipt mismatch; pending event retained')
            with self._open() as db:
                db.execute('DELETE FROM outbox WHERE id=?',(claim.source_event_id,))
            acknowledged += 1
        return acknowledged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db',required=True)
    parser.add_argument('--state-dir',required=True)
    parser.add_argument('--device-uid',required=True)
    parser.add_argument('--include-history',action='store_true')
    parser.add_argument('--resume-after-investigation',action='store_true')
    args=parser.parse_args()
    collector=HermesIncremental(args.source_db,args.state_dir,args.device_uid)
    if args.resume_after_investigation:
        collector.resume_after_investigation()
    result=collector.scan(include_history=args.include_history)
    result['pending']=len(collector.pending())
    print(json.dumps(result))


if __name__ == '__main__':
    main()
