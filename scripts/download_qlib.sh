#!/bin/sh
# Download a verified Qlib snapshot from chenditc/investment_data.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RELEASE_BASE=https://github.com/chenditc/investment_data/releases
tag=latest
destination=data/qlib-community
check_only=0
download_only=0
resume=0
metadata_dir=
lock_dir=
stage_dir=

usage() {
    cat <<'HELP'
用法：sh download_qlib.sh [选项]

  --tag YYYY-MM-DD   下载指定发布版本；默认 latest
  --dest DIR        保存目录；默认当前目录的 data/qlib-community
  --check-only      只查询版本、行情截止日、大小和 SHA256, 不下载大包
  --download-only   下载并校验, 暂不解压
  --resume          继续该版本上次保留的未完成目录
  --help            显示说明

依赖：curl 和 Python 3.12+（优先使用工具箱或当前目录的 .venv/bin/python）。
输出：DIR/发布日期/{qlib_bin.tar.gz,qlib_bin.manifest.json,cn_data/}
已有同版本目录时停止, 避免覆盖或混合不同数据快照。
HELP
}

fail() { printf '错误：%s\n' "$*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do
    case "$1" in
        --tag|--dest)
            [ "$#" -ge 2 ] && [ -n "$2" ] || fail "$1 缺少参数"
            case "$1" in --tag) tag=$2 ;; --dest) destination=$2 ;; esac
            shift 2 ;;
        --check-only) check_only=1; shift ;;
        --download-only) download_only=1; shift ;;
        --resume) resume=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) fail "未知参数：$1（使用 --help 查看说明）" ;;
    esac
done

command -v curl >/dev/null 2>&1 || fail '未找到 curl'
if [ -n "${QLIB_PYTHON:-}" ]; then
    python=$QLIB_PYTHON
elif [ -x "$SCRIPT_DIR/../.venv/bin/python" ]; then
    python=$SCRIPT_DIR/../.venv/bin/python
elif [ -x .venv/bin/python ]; then
    python=.venv/bin/python
else
    python=python3
fi
command -v "$python" >/dev/null 2>&1 || fail '未找到 Python；可设置 QLIB_PYTHON'
"$python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else "需要 Python 3.12+；可设置 QLIB_PYTHON 指向本机 Python 3.12")'

# JSON, hashing and safe extraction use only the Python standard library.
python_task() {
    "$python" - "$@" <<'PY'
import datetime
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

def valid_tag(value):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('发布版本必须是 YYYY-MM-DD')
    datetime.date.fromisoformat(value)
    return value

def manifest(path, tag):
    info = json.loads(Path(path).read_text(encoding='utf-8'))
    if info.get('release_tag') != tag:
        raise ValueError('清单的 release_tag 与下载版本不一致')
    size = info['archive_size_bytes']
    if type(size) is not int or size <= 0:
        raise ValueError('清单缺少有效的 archive_size_bytes')
    sha = info['archive_sha256']
    if not isinstance(sha, str) or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', sha):
        raise ValueError('清单缺少有效的 archive_sha256')
    trade_date = valid_tag(info['target_trade_date'])
    return info, size, sha.split(':', 1)[1].lower(), trade_date

def run():
    mode, *args = sys.argv[1:]
    if mode == 'tag':
        print(valid_tag(args[0]))
    elif mode == 'resolve':
        url = urlparse(args[0])
        prefix = '/chenditc/investment_data/releases/tag/'
        if url.scheme != 'https' or url.netloc != 'github.com' or not url.path.startswith(prefix):
            raise ValueError('latest 未重定向到预期的社区发布页')
        print(valid_tag(url.path[len(prefix):]))
    elif mode == 'manifest':
        _, size, sha, trade_date = manifest(*args)
        print(size, sha, trade_date)
    elif mode == 'verify':
        manifest_path, tag, archive_path = args
        _, size, sha, _ = manifest(manifest_path, tag)
        archive = Path(archive_path)
        if archive.stat().st_size != size:
            raise ValueError(f'数据包大小不符：期望 {size}, 实际 {archive.stat().st_size}')
        with archive.open('rb') as handle:
            actual_sha = hashlib.file_digest(handle, 'sha256').hexdigest()
        if actual_sha != sha:
            raise ValueError(f'SHA256 不符：期望 {sha}, 实际 {actual_sha}')
        print('数据包大小和 SHA256 均通过校验。')
    elif mode == 'resume':
        old_manifest, new_manifest, tag, archive_path = args
        if Path(old_manifest).is_symlink() or Path(archive_path).is_symlink():
            raise ValueError('未完成目录中的清单或数据包不能是链接')
        old, size, sha, _ = manifest(old_manifest, tag)
        new, _, _, _ = manifest(new_manifest, tag)
        if old != new:
            raise ValueError('上次清单与当前发布清单不同, 不能续传混合快照')
        archive = Path(archive_path)
        current_size = archive.stat().st_size if archive.exists() else 0
        if current_size > size:
            raise ValueError('未完成包比清单记录的大小更大, 不能续传')
        if current_size == size:
            with archive.open('rb') as handle:
                if hashlib.file_digest(handle, 'sha256').hexdigest() != sha:
                    raise ValueError('已下载包的 SHA256 不符, 不能续传')
            print('complete')
        else:
            print('partial')
    elif mode == 'extract':
        archive_path, output_path, manifest_path, tag = args
        _, _, _, trade_date = manifest(manifest_path, tag)
        output = Path(output_path)
        output.mkdir()
        # Reject traversal, links and special files before writing any members.
        with tarfile.open(archive_path, 'r:gz') as archive:
            members = archive.getmembers()
            roots = set()
            seen = set()
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts or not path.parts:
                    raise ValueError(f'归档包含不安全的路径：{member.name}')
                if not (member.isdir() or member.isfile()):
                    raise ValueError(f'归档包含链接或特殊文件：{member.name}')
                normalized = str(path)
                if normalized in seen:
                    raise ValueError(f'归档包含重复路径：{member.name}')
                seen.add(normalized)
                roots.add(path.parts[0])
            if len(roots) != 1:
                raise ValueError('归档必须包含一个独立顶层数据目录')
            root = next(iter(roots))
            for required in [f'{root}/calendars/day.txt', f'{root}/instruments/all.txt']:
                if required not in seen:
                    raise ValueError(f'归档缺少 Qlib 必要文件：{required}')
            if not any(name.startswith(f'{root}/features/') and name.endswith('.day.bin') for name in seen):
                raise ValueError('归档缺少 Qlib 二进制行情数据')
            archive.extractall(output, members=members, filter='data')
        nested = output / root
        # Publish the actual Qlib root as cn_data, independent of archive root name.
        temporary = output.with_name('unpacked_root')
        nested.rename(temporary)
        output.rmdir()
        temporary.rename(output)
        dates = (output / 'calendars/day.txt').read_text().splitlines()
        if not dates or dates != sorted(set(dates)):
            raise ValueError('交易日历为空、重复或未排序')
        for date in dates:
            valid_tag(date)
        if dates[-1] != trade_date:
            raise ValueError('交易日历末日与清单 target_trade_date 不一致')
        print(f'解压完成, 交易日历范围：{dates[0]} 至 {dates[-1]}')
    else:
        raise ValueError(f'未知内部操作：{mode}')

try:
    run()
except Exception as exc:
    print(f'错误：{exc}', file=sys.stderr)
    sys.exit(1)
PY
}

cleanup() {
    if [ -n "$metadata_dir" ]; then
        "$python" -c 'import shutil,sys; shutil.rmtree(sys.argv[1])' "$metadata_dir"
    fi
    if [ -n "$lock_dir" ]; then rmdir "$lock_dir"; fi
    if [ -n "$stage_dir" ] && [ -d "$stage_dir" ]; then
        printf '未完成的数据保留在：%s\n' "$stage_dir" >&2
    fi
}
trap cleanup 0
trap 'exit 130' 2
trap 'exit 143' 15

fetch() {
    curl --fail --location --show-error --retry 3 --retry-delay 2 \
        --connect-timeout 20 --proto '=https' --proto-redir '=https' "$@"
}

if [ "$tag" = latest ]; then
    printf '正在查询社区最新发布版本…\n'
    latest_url=$(fetch --silent --max-time 120 --output /dev/null \
        --write-out '%{url_effective}' "$RELEASE_BASE/latest")
    tag=$(python_task resolve "$latest_url")
else
    tag=$(python_task tag "$tag")
fi

metadata_dir=$(mktemp -d "${TMPDIR:-/tmp}/qlib-download.XXXXXXXX")
release_url=$RELEASE_BASE/download/$tag
fetch --silent --max-time 120 --output "$metadata_dir/qlib_bin.manifest.json" \
    "$release_url/qlib_bin.manifest.json"
details=$(python_task manifest "$metadata_dir/qlib_bin.manifest.json" "$tag")
# The helper emits only a positive integer, hexadecimal digest, and ISO date.
set -- $details
printf '发布版本：%s\n行情截止日：%s\n压缩包大小：%s bytes\nSHA256：%s\n' "$tag" "$3" "$1" "$2"
printf '数据包地址：%s/qlib_bin.tar.gz\n' "$release_url"
[ "$check_only" -eq 0 ] || exit 0

mkdir -p -- "$destination"
destination=$(CDPATH= cd -- "$destination" && pwd)
final_dir=$destination/$tag
[ ! -e "$final_dir" ] && [ ! -L "$final_dir" ] || fail "目录已存在：${final_dir}；请使用已有数据或指定新的 --dest"
candidate_lock=$destination/.$tag.lock
mkdir "$candidate_lock" 2>/dev/null || fail "该版本已有下载任务或遗留锁：$candidate_lock"
lock_dir=$candidate_lock
[ ! -e "$final_dir" ] && [ ! -L "$final_dir" ] || fail "目录已存在：$final_dir"
if [ "$resume" -eq 1 ]; then
    set -- "$destination/.$tag.partial."*
    [ "$#" -eq 1 ] && [ -d "$1" ] && [ ! -L "$1" ] || fail '续传需要该版本恰好存在一个未完成目录'
    stage_dir=$1
    [ ! -e "$stage_dir/cn_data" ] && [ ! -L "$stage_dir/cn_data" ] && \
        [ ! -e "$stage_dir/unpacked_root" ] && [ ! -L "$stage_dir/unpacked_root" ] || fail '该目录曾开始解压, 请先检查保留目录, 避免覆盖'
    state=$(python_task resume "$stage_dir/qlib_bin.manifest.json" \
        "$metadata_dir/qlib_bin.manifest.json" "$tag" "$stage_dir/qlib_bin.tar.gz")
    if [ "$state" = complete ]; then
        printf '发现已下载完整包, 跳过重复下载。\n'
    else
        printf '正在继续下载数据包…\n'
        fetch --continue-at - --max-time 3600 --output "$stage_dir/qlib_bin.tar.gz" "$release_url/qlib_bin.tar.gz"
    fi
else
    stage_dir=$(mktemp -d "$destination/.$tag.partial.XXXXXXXX")
    cp "$metadata_dir/qlib_bin.manifest.json" "$stage_dir/qlib_bin.manifest.json"
    printf '正在下载数据包…\n'
    fetch --max-time 3600 --output "$stage_dir/qlib_bin.tar.gz" "$release_url/qlib_bin.tar.gz"
fi
python_task verify "$stage_dir/qlib_bin.manifest.json" "$tag" "$stage_dir/qlib_bin.tar.gz"
if [ "$download_only" -eq 0 ]; then
    printf '正在解压…\n'
    python_task extract "$stage_dir/qlib_bin.tar.gz" "$stage_dir/cn_data" \
        "$stage_dir/qlib_bin.manifest.json" "$tag"
fi
mv "$stage_dir" "$final_dir"
stage_dir=
printf '下载完成：%s\n' "$final_dir"
if [ "$download_only" -eq 0 ]; then
    printf '供 read_qlib_prices 使用的数据目录：%s/cn_data\n' "$final_dir"
fi
