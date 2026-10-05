#!/bin/sh
# 下载 SEC companyfacts ZIP；解析和入库由 quanttoolskit 的 Python 接口完成。
set -eu

# 用环境变量配置，无命令行参数；data 默认位于执行命令的当前目录。
: "${EDGAR_IDENTITY:?请设置 EDGAR_IDENTITY，例如：姓名 邮箱地址}"
SEC_DATA_DIR="${SEC_DATA_DIR:-data}"
SEC_URL="https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"

for tool in curl unzip; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf '缺少依赖：%s\n' "$tool" >&2
        exit 1
    fi
done

mkdir -p "$SEC_DATA_DIR"
archive="$SEC_DATA_DIR/companyfacts.zip"
partial="$archive.part"

# 只续传未完成的 .part；重新运行时不会追加到已经校验完成的 ZIP。
# 下载或校验失败均保留旧 ZIP，防止下游解析器读取半成品。
printf '下载 SEC companyfacts 到：%s\n' "$archive"
curl --fail --location --connect-timeout 30 \
    --retry 5 --retry-delay 3 --continue-at - \
    -H "User-Agent: $EDGAR_IDENTITY" \
    --output "$partial" "$SEC_URL"

printf '核验 ZIP 完整性（CRC）……\n'
if ! unzip -tq "$partial"; then
    printf 'ZIP 校验失败，旧文件未更新。来源可能已变化；删除 %s 后重新运行。\n' "$partial" >&2
    exit 1
fi

mv -f "$partial" "$archive"
printf '下载并校验完成：%s\n' "$archive"
