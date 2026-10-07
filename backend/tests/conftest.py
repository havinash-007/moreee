import os
import pathlib
import shutil
import socket
import subprocess
import tempfile

import pytest

os.environ.setdefault("CATALOGUE_AUTO_REFRESH", "false")  # tests must never hit the network on startup

PG_BIN = pathlib.Path(os.getenv("PG_BIN") or (pathlib.Path.home() / ".cache" / "pg" / "pgroot" / "bin"))


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


@pytest.fixture(scope="session")
def pg_url():
    """A throwaway local PostgreSQL (binaries from PG_BIN or ~/.cache/pg). None when unavailable, so Postgres tests skip."""
    if os.getenv("TEST_DATABASE_URL"):
        yield os.environ["TEST_DATABASE_URL"]
        return
    if not (PG_BIN / "initdb").exists():
        yield None
        return
    d = tempfile.mkdtemp(prefix="osspg")
    port = _free_port()
    env = dict(os.environ, LC_ALL="C")
    subprocess.run([str(PG_BIN / "initdb"), "-D", d, "-A", "trust", "-U", "postgres", "-E", "UTF8"], check=True, capture_output=True, env=env)
    subprocess.run([str(PG_BIN / "pg_ctl"), "-D", d, "-o", f"-p {port} -k {d} -c listen_addresses=127.0.0.1", "-w", "start", "-l", f"{d}/log"], check=True, capture_output=True, env=env)
    yield f"postgresql://postgres@127.0.0.1:{port}/postgres"
    subprocess.run([str(PG_BIN / "pg_ctl"), "-D", d, "-m", "immediate", "stop"], capture_output=True, env=env)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(autouse=True)
def _backend(request, monkeypatch):
    """OSS_TEST_PG=1 runs the WHOLE suite on Postgres instead of SQLite (parity check). Tests that ask for `pg_url` choose it themselves."""
    if os.getenv("OSS_TEST_PG") and "pg_url" not in request.fixturenames:
        url = request.getfixturevalue("pg_url")
        if url:
            from backend import config, db
            monkeypatch.setattr(config, "DATABASE_URL", url)
            db.reset_for_tests()
    yield
