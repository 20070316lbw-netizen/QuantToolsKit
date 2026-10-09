"""打包契约：下载脚本必须随 wheel 进入消费项目环境。

`scripts/` 只配置 source-include 时仅进入 sdist；`uv add` / `pip install`
安装的是 wheel, 消费项目里看不到脚本。这些用例把 wheel 与 sdist 两条路径
都固定下来, 避免再次出现“装成依赖后 download_sec.sh 不见了”。
"""

import stat
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_NAMES = ("download_sec.sh", "download_qlib.sh")


def _build_backend_config() -> dict:
    """读取 pyproject.toml 里的 uv_build 配置。"""
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["tool"]["uv"]["build-backend"]


def test_scripts_are_installed_into_the_consumer_environment():
    """data.scripts 把 scripts/ 写进 wheel 的 .data/scripts, 安装后落到 venv/bin。"""
    assert _build_backend_config()["data"]["scripts"] == "scripts"


def test_scripts_stay_in_the_source_distribution():
    """source-include 只覆盖 sdist, 与 wheel 的 data 配置必须同时保留。"""
    assert "scripts/**" in _build_backend_config()["source-include"]


def test_download_scripts_are_runnable_shell_files():
    """两个下载脚本存在、可执行, 并用 /bin/sh 作为解释器。"""
    for name in SCRIPT_NAMES:
        path = ROOT / "scripts" / name
        assert path.read_text(encoding="utf-8").startswith("#!/bin/sh\n")
        assert path.stat().st_mode & stat.S_IXUSR
