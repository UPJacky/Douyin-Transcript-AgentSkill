# 贡献指南

## 本地验证

CI 使用项目的 `uv.lock`，矩阵覆盖 Windows、macOS 和 Linux，以及 Python 3.11 和 3.12。提交前可在仓库根目录运行相同检查：

```sh
uv lock --project skills/douyin-transcript --check
uv sync --project skills/douyin-transcript --locked --group dev
uv run --project skills/douyin-transcript --locked --group dev ruff check scripts skills/douyin-transcript/src skills/douyin-transcript/scripts tests
uv run --project skills/douyin-transcript --locked --group dev pytest -q
python scripts/check_sensitive_files.py
```

测试使用假网页响应、注入的依赖和本机回环 socket，不需要抖音账号、真实视频、ASR 模型或 Chromium。请勿为跑 CI 下载模型、安装浏览器或将真实媒体、Cookie、浏览器 profile、模型文件、转写稿提交到仓库。

CI 只验证锁定依赖、静态检查和离线测试；它不验证真实抖音页面、实际 ASR 识别质量或发布安装流程。贡献说明这些功能时，请把未实测的部分明确标为未验证，并避免提交私人媒体或账号数据作为复现材料。
