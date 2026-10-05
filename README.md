# QuantToolsKit

[![CI](https://github.com/20070316lbw-netizen/QuantToolsKit/actions/workflows/ci.yml/badge.svg)](https://github.com/20070316lbw-netizen/QuantToolsKit/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/20070316lbw-netizen/QuantToolsKit/branch/main/graph/badge.svg)](https://codecov.io/gh/20070316lbw-netizen/QuantToolsKit)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue?logo=python&logoColor=white)](pyproject.toml)
[![License](https://img.shields.io/github/license/20070316lbw-netizen/QuantToolsKit)](LICENSE)
[![Ruff](https://img.shields.io/badge/lint%20%26%20format-Ruff-D7FF64?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)
[![Last commit](https://img.shields.io/github/last-commit/20070316lbw-netizen/QuantToolsKit)](https://github.com/20070316lbw-netizen/QuantToolsKit/commits/main/)

个人量化工具箱。点击模块目录查看各模块的独立使用说明。
全项目计算接口遵循 [MultiIndex DataFrame 数据结构约定](docs/data-structure.md)。
覆盖率统计与徽章配置见 [验证说明](docs/coverage.md)。

## 模块目录

| 模块 | 内容 | 状态 |
| --- | --- | --- |
| [data](src/quanttoolskit/data/README.md) | 成员准备、SEC 压缩包下载、行情与基本面获取、DuckDB 入库及查询 | 已实现 |
| [returns](docs/returns.md) | 简单与对数收益率：历史特征与未来标签 | 已实现 |
| [volatility](docs/volatility.md) | 滚动波动率：历史波动特征与未来波动标签 | 已实现 |
| [indicators](src/quanttoolskit/indicators/README.md) | 技术指标 | 占位 |
| [factors](src/quanttoolskit/factors/README.md) | 滚动对数动量、经典 12-1 动量 | 已实现 |
| [portfolio](src/quanttoolskit/portfolio/README.md) | 权重、调仓与组合操作 | 占位 |
| [performance](src/quanttoolskit/performance/README.md) | 收益、回撤与绩效统计 | 占位 |
| [plotting](src/quanttoolskit/plotting/README.md) | 绘图 | 占位 |

```text
src/quanttoolskit/
├── data/          # 数据获取、存储、查询、预处理
├── indicators/    # 技术指标
├── factors/       # 因子计算
├── portfolio/     # 权重、调仓、组合操作
├── performance/   # 收益、回撤、绩效统计
├── plotting/      # 绘图
├── returns.py     # 简单与对数收益率：历史特征与未来标签
└── volatility.py  # 滚动波动率：历史波动特征与未来波动标签
```

## 安装

开发时在消费项目（如 `chores`）里安装本地可编辑依赖，修改工具箱后直接生效：

```bash
uv add --editable ../QuantToolsKit
```

仓库版本的安装方式：

```bash
uv add "quanttoolskit @ git+https://github.com/20070316lbw-netizen/QuantToolsKit.git"
```

安装后从 [data 使用说明](src/quanttoolskit/data/README.md#快速开始) 开始；价格特征
与标签见 [returns](docs/returns.md) 和 [volatility](docs/volatility.md)。

## 许可证

本项目采用 [MIT License](LICENSE)。
