# 覆盖率与徽章

[返回项目首页](../README.md)

首页展示 CI、Coverage、Python 最低版本、许可证、Ruff 和最近提交时间。
Python 与 Ruff 为项目声明；CI、Coverage、许可证和提交时间来自对应服务。

## 本地覆盖率

```bash
uv sync --locked --all-groups
uv run pytest --cov=quanttoolskit --cov-branch --cov-report=term-missing --cov-report=html
```

统计整个 quanttoolskit 包，包括未执行的模块，启用分支覆盖率。
打开 htmlcov/index.html 查看逐文件和分支结果。报告不提交到仓库。
覆盖率表示测试执行到的代码比例，不代表公式或业务逻辑必然正确。

## CI 与动态徽章

CI 每次生成终端、XML、HTML 报告，并把概要写到 Actions 的 Summary。
完整报告保存为 coverage-reports artifact，同时上传 Codecov，用于更新 main 徽章。

上传通过 GitHub OIDC 认证（id-token: write），无需在仓库保存 CODECOV_TOKEN。
参考 [Codecov Action 的 OIDC 说明](https://github.com/codecov/codecov-action#using-oidc)。
首次上传后才能验证 Codecov 端接收情况和徽章百分比；此前可能显示 unknown。
如果服务提示仓库尚未激活，需要在 Codecov 登录 GitHub 并启用本仓库。
上传失败会在 Actions 中保留告警，不阻断代码检查、测试和构建。
HTML/XML 报告仍已保存，可通过 Actions 查看。首次上传返回 Repository not found 时，
需先在 Codecov 启用本仓库，再重新运行 CI。

实现见 [ci.yml](../.github/workflows/ci.yml)。
