# P6：286 个新增归档成员的内容分类复核

日期：2026-10-11
范围：`unbound-license-candidate-hashes-2026-10-11-final.json` 中 286 条 `evidence_bound_before=false`、`evidence_bound_after=true` 的成员记录。

## 校验方法与边界

- 将每条记录的包名、版本、制品类型、URL、制品 SHA-256 和大小与 `skills/douyin-transcript/uv.lock` 对应项逐一比对。
- 只读私有 SHA 缓存；对 152 个唯一制品重新计算制品 SHA-256，并在内存中读取归档成员，重新核对精确路径、成员大小和成员 SHA-256。没有解包到磁盘、联网或更改证据 JSON。
- 286 条记录来自 152 个唯一制品：118 个 wheel 和 34 个 sdist；按原始记录数为 181 条 wheel、105 条 sdist。
- 286 个成员均为文本格式：284 个 UTF-8 文本、2 个 RTF 文本；未发现二进制成员。按 `(package, member SHA-256)` 去重后为 92 组，成员正文共有 90 个不同 SHA-256。
- 以下是内容和路径类型分类，不判断许可是否适用于项目的分发物，也不作法律结论或修改 `licenseDeclared` / `licenseConcluded`。

## 分类结果

| 内容类别 | 记录数 | 去重后 `(package, member SHA-256)` | 判断依据与代表路径 |
|---|---:|---:|---|
| 可识别的许可证正文 | 223 | 68 | 以正文中的许可授予/条款和对应文件内容确认；如 `onnxruntime/LICENSE`、`packaging-26.3.dist-info/licenses/LICENSE.APACHE`、`numpy-2.5.3/numpy/_core/src/common/pythoncapi-compat/COPYING`。另有 2 条 RTF 格式许可证正文，路径为 `numpy-2.4.6/vendored-meson/meson/packaging/License.rtf` 与 `numpy-2.5.3/vendored-meson/meson/packaging/License.rtf`。 |
| NOTICE / 第三方声明文档 | 8 | 2 | `onnxruntime/ThirdPartyNotices.txt`；8 条归档记录归并为 2 份不同正文。 |
| 作者/贡献者名单 | 16 | 4 | 如 `av-15.1.0.dist-info/licenses/AUTHORS.rst`、`pygments-2.21.0.dist-info/licenses/AUTHORS`、`pytest-8.4.2.dist-info/licenses/AUTHORS`。 |
| 源码或构建文件误报 | 26 | 9 | 名称含 `license` / `copyright` 或位于 `licenses` 路径，但正文是程序/构建代码；例如 `packaging-26.3/src/packaging/licenses/_spdx.py`、`ruff-0.14.14/crates/ruff_linter/src/rules/flake8_copyright/rules/missing_copyright_notice.rs`。`av-15.1.0.dist-info/licenses/AUTHORS.py` 可解析为 Python AST，是程序文件，不是纯作者名单。 |
| 文档、模板误报 | 8 | 6 | 例如 `fsspec-2026.9.0/docs/source/copying.rst` 是文档，NumPy 的 `doc/source/license.rst` 是短文档入口；`packaging-26.3/docs/licenses.rst`、Meson 的 license HTML 模板和生成说明也不是许可证正文。 |
| 许可标识/短引用，不含完整条款 | 3 | 2 | `packaging-26.3/LICENSE` 与其 `dist-info/licenses/LICENSE` 内容相同；`click-8.5.0/docs/license.md` 是短许可标识。 |
| 版权归属短声明，不含完整许可授予 | 2 | 1 | NumPy 两个版本中的 `numpy/random/src/splitmix64/LICENSE.md` 正文相同，属于短版权/许可提示。 |
| **合计** | **286** | **92** | 与候选清单总数及去重数一致。 |

## 对证据处理的建议

1. 将“路径候选”与“正文类型”分开记录：`AUTHORS.py`、`_spdx.py`、源码中的 copyright 规则、文档入口和模板不应仅因路径命中就作为许可证正文描述。
2. 许可证正文、NOTICE、短引用、作者名单分别保留类型；按包名和成员 SHA 去重可减少重复阅读，但各制品中的精确 artifact/path/hash 绑定仍应保持。
3. RTF 要作为结构化文本识别。仅用 NUL/控制字符比例判断二进制会把这 2 个 RTF 许可证误判为二进制。
4. 这次分类只证明缓存归档中的成员内容与已锁定制品及保存的成员 SHA 相符。它不能证明某份许可证适用于最终发布包；该问题仍需结合实际打包/分发清单和所有者决定。

## 可复核输入

- 候选清单 SHA-256：`c13a600cb2faa017a050502ef606f030802d3af558340312459fd30c877ead66`
- `uv.lock` SHA-256：`f4fc838d6f52555ca03ccf378c67e2a988666928904ff14bfab6d4af7c88f31b`
- 缓存位置：`<local user path>`（本次仅读取）
