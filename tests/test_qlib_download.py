"""Offline end-to-end checks using small release assets and a fake transport."""

import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "download_qlib.sh"
TAG = "2026-10-07"


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="qlib-fetch-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        self.destination = self.root / "downloads"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        transport = self.bin / "curl"
        transport.write_text(
            f"#!{sys.executable}\n"
            + """
import os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
url = args[-1]
root = Path(os.environ['FIXTURE_ASSETS'])
if url.endswith('/latest'):
    print('https://github.com/chenditc/investment_data/releases/tag/2026-10-07', end='')
else:
    source = root / url.rsplit('/', 1)[-1]
    if not source.exists():
        sys.exit(22)
    target = Path(args[args.index('--output') + 1])
    if '--continue-at' in args:
        offset = target.stat().st_size if target.exists() else 0
        with target.open('ab') as handle:
            handle.write(source.read_bytes()[offset:])
    else:
        shutil.copyfile(source, target)
""",
            encoding="utf-8",
        )
        transport.chmod(0o755)
        self.env = dict(
            os.environ,
            PATH=f"{self.bin}:{os.environ['PATH']}",
            FIXTURE_ASSETS=str(self.assets),
            QLIB_PYTHON=sys.executable,
        )
        self.make_assets()

    def make_assets(self, extra=None, target_date="2026-09-30"):
        archive_path = self.assets / "qlib_bin.tar.gz"
        content = {
            "qlib_bin/calendars/day.txt": b"2026-09-29\n2026-09-30\n",
            "qlib_bin/instruments/all.txt": b"SH600000\t2026-09-29\t2026-09-30\n",
            "qlib_bin/features/sh600000/close.day.bin": struct.pack("<fff", 0, 10, 11),
        }
        if extra:
            content.update(extra)
        with tarfile.open(archive_path, "w:gz") as archive:
            for name, value in content.items():
                member = tarfile.TarInfo(name)
                member.size = len(value)
                archive.addfile(member, io.BytesIO(value))
        manifest = {
            "release_tag": TAG,
            "target_trade_date": target_date,
            "archive_size_bytes": archive_path.stat().st_size,
            "archive_sha256": "sha256:"
            + hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        }
        (self.assets / "qlib_bin.manifest.json").write_text(json.dumps(manifest))

    def run_script(self, *args):
        return subprocess.run(
            ["sh", str(SCRIPT), "--dest", str(self.destination), *args],
            env=self.env,
            text=True,
            capture_output=True,
            timeout=15,
        )

    def test_latest_download_extracts_qlib_root(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.destination / TAG
        self.assertTrue((output / "qlib_bin.tar.gz").is_file())
        self.assertTrue((output / "qlib_bin.manifest.json").is_file())
        self.assertEqual(
            (output / "cn_data/calendars/day.txt").read_text(),
            "2026-09-29\n2026-09-30\n",
        )
        self.assertIn("供 read_qlib_prices 使用的数据目录", result.stdout)
        self.assertFalse(list(self.destination.glob(".*.lock")))

    def test_check_only_does_not_download_archive_or_create_destination(self):
        result = self.run_script("--check-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("行情截止日：2026-09-30", result.stdout)
        self.assertFalse(self.destination.exists())

    def test_download_only_verifies_without_extracting(self):
        result = self.run_script("--tag", TAG, "--download-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.destination / TAG / "qlib_bin.tar.gz").is_file())
        self.assertFalse((self.destination / TAG / "cn_data").exists())

    def test_existing_snapshot_is_preserved(self):
        output = self.destination / TAG
        output.mkdir(parents=True)
        sentinel = output / "existing.txt"
        sentinel.write_text("do not change")
        result = self.run_script("--tag", TAG)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("目录已存在", result.stderr)
        self.assertEqual(sentinel.read_text(), "do not change")
        self.assertEqual(list(output.iterdir()), [sentinel])

    def test_corrupt_archive_is_not_published_or_extracted(self):
        archive = self.assets / "qlib_bin.tar.gz"
        data = bytearray(archive.read_bytes())
        data[-1] ^= 1  # Same byte count, wrong digest.
        archive.write_bytes(data)
        result = self.run_script("--tag", TAG)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA256 不符", result.stderr)
        self.assertFalse((self.destination / TAG).exists())
        self.assertFalse(list(self.destination.glob(".*.lock")))

    def test_path_traversal_is_rejected_even_with_matching_digest(self):
        self.make_assets(extra={"qlib_bin/../../outside.txt": b"escape"})
        result = self.run_script("--tag", TAG)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("不安全的路径", result.stderr)
        self.assertFalse((self.destination / TAG).exists())
        self.assertFalse((self.root / "outside.txt").exists())
        self.assertFalse(list(self.destination.rglob("outside.txt")))

    def test_calendar_manifest_mismatch_is_not_published(self):
        self.make_assets(target_date="2026-09-29")
        result = self.run_script("--tag", TAG)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("交易日历末日", result.stderr)
        self.assertFalse((self.destination / TAG).exists())

    def test_invalid_version_is_rejected_before_network_or_files(self):
        result = self.run_script("--tag", "../../escape")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("YYYY-MM-DD", result.stderr)
        self.assertFalse(self.destination.exists())

    def test_release_manifest_mismatch_is_rejected_before_big_download(self):
        path = self.assets / "qlib_bin.manifest.json"
        manifest = json.loads(path.read_text())
        manifest["release_tag"] = "2026-10-06"
        path.write_text(json.dumps(manifest))
        result = self.run_script("--tag", TAG)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("release_tag", result.stderr)
        self.assertFalse(self.destination.exists())

    def test_archive_size_mismatch_is_rejected(self):
        path = self.assets / "qlib_bin.tar.gz"
        path.write_bytes(path.read_bytes()[:10])
        result = self.run_script("--tag", TAG)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("数据包大小不符", result.stderr)
        self.assertFalse((self.destination / TAG).exists())

    def test_symlink_is_rejected(self):
        path = self.assets / "qlib_bin.tar.gz"
        with tarfile.open(path, "r:gz") as archive:
            existing = [
                (m, archive.extractfile(m).read()) for m in archive.getmembers()
            ]
        with tarfile.open(path, "w:gz") as archive:
            for member, data in existing:
                archive.addfile(member, io.BytesIO(data))
            link = tarfile.TarInfo("qlib_bin/escape")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../outside"
            archive.addfile(link)
        manifest_path = self.assets / "qlib_bin.manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["archive_size_bytes"] = path.stat().st_size
        manifest["archive_sha256"] = (
            "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        )
        manifest_path.write_text(json.dumps(manifest))
        result = self.run_script("--tag", TAG)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("链接或特殊文件", result.stderr)
        self.assertFalse((self.destination / TAG).exists())

    def test_resume_reuses_completed_archive(self):
        partial = self.destination / f".{TAG}.partial.fixture"
        partial.mkdir(parents=True)
        for path in self.assets.iterdir():
            shutil.copyfile(path, partial / path.name)
        result = self.run_script("--tag", TAG, "--resume")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("跳过重复下载", result.stdout)
        self.assertFalse(partial.exists())
        self.assertTrue(
            (self.destination / TAG / "cn_data/calendars/day.txt").is_file()
        )

    def test_resume_does_not_guess_between_multiple_partial_downloads(self):
        for suffix in ["one", "two"]:
            (self.destination / f".{TAG}.partial.{suffix}").mkdir(parents=True)
        result = self.run_script("--tag", TAG, "--resume")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("恰好存在一个", result.stderr)
        self.assertFalse((self.destination / TAG).exists())

    def test_resume_partial_archive(self):
        partial = self.destination / f".{TAG}.partial.fixture"
        partial.mkdir(parents=True)
        shutil.copyfile(
            self.assets / "qlib_bin.manifest.json", partial / "qlib_bin.manifest.json"
        )
        (partial / "qlib_bin.tar.gz").write_bytes(
            (self.assets / "qlib_bin.tar.gz").read_bytes()[:10]
        )
        result = self.run_script("--tag", TAG, "--resume")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("正在继续下载", result.stdout)
        self.assertEqual(
            (self.destination / TAG / "qlib_bin.tar.gz").read_bytes(),
            (self.assets / "qlib_bin.tar.gz").read_bytes(),
        )

    def test_resume_rejects_changed_manifest(self):
        partial = self.destination / f".{TAG}.partial.fixture"
        partial.mkdir(parents=True)
        for path in self.assets.iterdir():
            shutil.copyfile(path, partial / path.name)
        saved = partial / "qlib_bin.manifest.json"
        info = json.loads(saved.read_text())
        info["archive_sha256"] = "sha256:" + "0" * 64
        saved.write_text(json.dumps(info))
        before = saved.read_bytes()
        result = self.run_script("--tag", TAG, "--resume")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("清单不同", result.stderr)
        self.assertEqual(saved.read_bytes(), before)
        self.assertFalse((self.destination / TAG).exists())

    def test_default_destination_is_under_callers_working_directory(self):
        result = subprocess.run(
            ["sh", str(SCRIPT), "--tag", TAG, "--download-only"],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (self.root / "data/qlib-community" / TAG / "qlib_bin.tar.gz").is_file()
        )


if __name__ == "__main__":
    unittest.main()
