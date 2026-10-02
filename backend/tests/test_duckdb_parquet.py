"""DuckDB behaviour tests: resource caps + Parquet-backed datasets (PART B4).

Cloud Run's disk is temporary and the container is small (2 GiB / 1 vCPU), so:
  * DuckDB must be capped (memory_limit / threads), and
  * a dataset may be served straight from Parquet via `read_parquet` instead of
    a writable DuckDB copy (nothing is ever loaded into pandas).

These run against a throwaway DuckDB connection and a Parquet export of the
committed store_master seed file, so they do not disturb the app's own catalog.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

import duckdb

from app.core import database
from app.core.config import DUCKDB_MEMORY_LIMIT, DUCKDB_THREADS, SEED_FILES


class DuckDbEngineTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="retailynx_duckdb_test_")
        self.seed = SEED_FILES["store_master"]
        if not self.seed.exists():
            self.skipTest(f"seed database not present: {self.seed}")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_parquet(self) -> Path:
        """Export the store_master seed table to Parquet in the temp dir."""
        parquet = Path(self._tmpdir) / "store_master.parquet"
        con = duckdb.connect(":memory:")
        try:
            con.execute(f"ATTACH '{self.seed.as_posix()}' AS src (READ_ONLY)")
            con.execute(
                f"COPY (SELECT * FROM src.store_details) TO '{parquet.as_posix()}' "
                "(FORMAT PARQUET)"
            )
        finally:
            con.close()
        return parquet

    def test_engine_settings_cap_memory_and_threads(self):
        con = duckdb.connect(":memory:")
        try:
            database._apply_engine_settings(con)
            memory = con.execute("SELECT current_setting('memory_limit')").fetchone()[0]
            threads = int(con.execute("SELECT current_setting('threads')").fetchone()[0])
        finally:
            con.close()
        # DuckDB normalises "1GB" to e.g. "953.6 MiB" / "1.0 GiB".
        self.assertIn("iB", memory)
        self.assertEqual(threads, DUCKDB_THREADS)
        self.assertEqual(DUCKDB_MEMORY_LIMIT, "1GB")  # the documented default

    def test_parquet_dataset_is_attachable_and_queryable(self):
        parquet = self._write_parquet()
        saved = database.PARQUET_FILES["store_master"]
        database.PARQUET_FILES["store_master"] = [parquet]
        con = duckdb.connect(":memory:")
        try:
            database._apply_engine_settings(con)
            database._attach_all(con)

            # The logical schema/table the whole app queries now exists...
            count = con.execute("SELECT COUNT(*) FROM store_master.store_details").fetchone()[0]
            self.assertGreater(count, 0)

            # ...backed by a VIEW over read_parquet (no data copy, no pandas).
            kind = con.execute(
                "SELECT table_type FROM information_schema.tables "
                "WHERE table_catalog='store_master' AND table_name='store_details'"
            ).fetchone()[0]
            self.assertEqual(kind.upper(), "VIEW")

            columns = {
                row[0]
                for row in con.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_catalog='store_master' AND table_name='store_details'"
                ).fetchall()
            }
            self.assertIn("adonis_store_code", columns)
            self.assertIn("brand_code", columns)

            # Parquet-backed store_master is read-only -> enrichment is skipped.
            self.assertFalse(database._store_master_is_writable())
        finally:
            database.PARQUET_FILES["store_master"] = saved
            con.close()

    def test_seed_file_is_used_read_only_when_no_working_copy_exists(self):
        """With no Parquet and no writable copy, the committed seed is attached."""
        saved = database.PARQUET_FILES["store_master"]
        saved_working = database.WORKING_FILES["store_master"]
        database.PARQUET_FILES["store_master"] = []
        database.WORKING_FILES["store_master"] = Path(self._tmpdir) / "does_not_exist.duckdb"
        con = duckdb.connect(":memory:")
        try:
            database._attach_all(con)
            count = con.execute("SELECT COUNT(*) FROM store_master.store_details").fetchone()[0]
            self.assertGreater(count, 0)
        finally:
            database.PARQUET_FILES["store_master"] = saved
            database.WORKING_FILES["store_master"] = saved_working
            con.close()

    def test_parquet_glob_accepts_flat_files_and_directories(self):
        from app.core import config

        parquet = self._write_parquet()
        saved_dir = config.DATA_DIR
        config.DATA_DIR = Path(self._tmpdir)
        try:
            # flat: <dataset>.parquet
            self.assertEqual(config.parquet_files_for("store_master"), [parquet])

            # nested: <dataset>/*.parquet
            nested = Path(self._tmpdir) / "tertiary_data"
            nested.mkdir()
            part = nested / "part-0.parquet"
            part.write_bytes(parquet.read_bytes())
            self.assertEqual(config.parquet_files_for("tertiary_data"), [part])

            # nothing on disk -> no files (and no exception)
            self.assertEqual(config.parquet_files_for("order_form"), [])
        finally:
            config.DATA_DIR = saved_dir


if __name__ == "__main__":
    unittest.main()