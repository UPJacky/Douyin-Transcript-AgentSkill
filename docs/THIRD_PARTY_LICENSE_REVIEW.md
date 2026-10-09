# 第三方许可与发行路径复核

- 日期：2026-10-09
- 范围：当前 `pyproject.toml` / `uv.lock` 中直接使用的 ASR、解码和浏览器依赖，以及固定 ASR 模型；这是技术来源与发行路径核对，不代替项目所有者的许可证决定或法律审阅。
- 当前交付形态：Skill 作为源代码目录分发，ASR / 浏览器是可选依赖；模型和浏览器由用户执行 setup 时分别下载。当前 Git 可见树未发现 `.whl`、模型权重或浏览器二进制，也没有项目 `LICENSE`。本清单不是完整的传递依赖 SBOM。

## 已核对的组件

| 组件 | 当前锁定版本或来源 | 上游声明 | 发行边界与未决事项 |
|---|---|---|---|
| faster-whisper | `1.2.1` | MIT；见 [v1.2.1 LICENSE](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/LICENSE) | 当前项目通过可选 `asr` extra 安装，仓库不包含其 wheel |
| Medium ASR 模型 | `Systran/faster-whisper-medium`，revision `08e178d48790749d25932bbc082711ddcfdfbc4f` | 固定 Hugging Face revision 页面声明 MIT；见[模型文件页](https://huggingface.co/Systran/faster-whisper-medium/tree/08e178d48790749d25932bbc082711ddcfdfbc4f) | setup 在用户本机下载模型；仓库不包含权重。该声明对应上游模型仓库，不是本项目的许可证 |
| Playwright Python | 锁文件当前解析 `1.63.0` | Apache-2.0；见 [v1.63.0 pyproject](https://github.com/microsoft/playwright-python/blob/v1.63.0/pyproject.toml) | 项目通过可选 `browser` extra 安装 Python 包；Playwright 文档说明浏览器二进制需另行安装，默认 Chromium 是其支持的开源构建，存放在本机缓存；当前仓库不包含浏览器文件。见[浏览器安装说明](https://playwright.dev/python/docs/browsers) |
| PyAV | `15.1.0` | PyAV 源码许可证为 BSD-3-Clause；见 [v15.1.0 LICENSE](https://github.com/PyAV-Org/PyAV/blob/v15.1.0/LICENSE.txt) 和 [PyPI 15.1.0 元数据](https://pypi.org/project/av/15.1.0/) | Windows wheel 已在仓库外临时环境安装，用于 SEC-31 动态验证；未随仓库分发。该 wheel 含 `libx264`、`libx265` DLL，PyAV 也报告对应编码器可用；这是 FFmpeg GPL 构建组件的强烈审查信号，但当前仍未提取 wheel 的完整 configure/build configuration 或确认 x264 商业许可例外。PyPI 为各平台提供链接 FFmpeg 的 wheel；其他目标平台尚未核查。不能仅凭 PyAV 的 BSD-3-Clause 标签判断所含二进制的义务 |

## 发布风险与对策

1. **PyAV wheel 的 FFmpeg 组件需要按目标平台核对。** FFmpeg 官方说明默认许可为 LGPL-2.1-or-later，组合 libx264/libx265 等 GPL 库会要求采用对应 GPL 构建；二进制再分发也需要准确的源码、配置和 notice 材料，见 [FFmpeg legal considerations](https://ffmpeg.org/legal.html)。Windows PyAV 15.1.0 wheel 已为本地动态验收而获取，并在 `av.libs` 中观察到 libx264/libx265 DLL 及可用编码器；尚未取得完整 build configuration 或确认商业许可例外，也未检查其余组件的 notice/源码材料；macOS/Linux wheel 也尚未检查。在这些事项核清前，不把 PyAV wheel 或包含它的二进制包纳入本项目发行。此观察不证明当前源代码树违法，也不构成法律意见。
2. **模型和浏览器不可并入本项目许可证。** 若未来将模型权重、Playwright 浏览器、PyAV wheel 或其 FFmpeg 动态库打进可执行包，需分别保留相应版权/许可文本，并按目标平台的实际二进制完成源代码与构建配置审查。当前源代码目录不打包这些二进制。
3. **项目自身许可证仍待所有者选择。** 由仓库所有者决定适用于本项目代码的许可证，并新增对应 `LICENSE`；本复核不替所有者选 MIT、Apache-2.0 或其他许可证。
4. **完成完整锁定依赖清单。** 发布前从 `uv.lock` 生成 SPDX SBOM，逐项确认直接与传递依赖的精确版本、许可证和 notice 文件；对每种支持平台的 PyAV wheel 保存 FFmpeg 版本、编译配置、组件清单及上游要求的源码/notice。

## 当前状态

- 上游代码、模型和浏览器 Python 包的初步许可证来源已记录。
- 项目 LICENSE、传递依赖 SBOM、PyAV wheel 内 FFmpeg 配置/notice，以及任何二进制再分发审查尚未完成。
- 在上述事项关闭前，P6 仍为 **NOT READY**。
