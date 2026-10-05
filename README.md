# QuantToolsKit

[![CI](https://github.com/20070316lbw-netizen/QuantToolsKit/actions/workflows/ci.yml/badge.svg)](https://github.com/20070316lbw-netizen/QuantToolsKit/actions/workflows/ci.yml)

个人量化工具箱。各模块的使用说明放在对应目录，点击下面的模块名查看。

## 模块目录

| 模块 | 内容 | 状态 |
| --- | --- | --- |
| [data](src/quanttoolskit/data/README.md) | 成员准备、SEC 压缩包下载、行情与基本面获取、DuckDB 入库及查询 | 已实现 |
| [indicators](src/quanttoolskit/indicators/README.md) | 技术指标 | 占位 |
| [factors](src/quanttoolskit/factors/README.md) | 因子计算 | 占位 |
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
└── plotting/      # 绘图
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

安装后从 [data 使用说明](src/quanttoolskit/data/README.md#快速开始) 开始。

## 许可证

本项目采用 [MIT License](LICENSE)。
