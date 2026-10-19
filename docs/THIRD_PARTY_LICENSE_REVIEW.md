# 第三方许可与发行路径复核

> **当前决策（2026-10-15）：** 用户不能确认其拥有或取得所有原创贡献采用 MIT 的授权；此前 MIT 候选不构成可用版权授权或发布决定。项目许可证未定，MIT 文本仅保存在内部草案且不纳入发行候选。首阶段发行范围为源码，支持目标为 Windows 11 x64、Python 3.11/3.12。第三方 SPDX `licenseConcluded` 仍为 `NOASSERTION`，本注记不构成发布批准。下方历史审阅内容保留。

- 日期：2026-10-13
- 范围：当前 `pyproject.toml` / `uv.lock` 中直接使用的 ASR、解码和浏览器依赖，以及固定 ASR 模型；这是技术来源与发行路径核对，不代替项目所有者的许可证决定或法律审阅。
- **截至 2026-10-13 的历史工作树快照：** Skill 以源目录存在，ASR / 浏览器列为可选依赖；模型和浏览器由用户执行 setup 时分别下载。这不代表所有者已批准任何分发。当时未发现 `.whl`、模型权重、浏览器二进制或项目根 `LICENSE`。2026-10-14 后续状态见本报告顶部，根 `LICENSE` 已创建，但权利归属仍待确认。完整锁定依赖组件盘点见 `docs/third-party-sbom.spdx.json`；本报告记录技术证据与发行边界，不代替所有者或法律审阅。
- **§279 P6 历史快照：** §268 已把 SPDX freshness 与 .NET build-output identity 检查接入 CI 源码；§271 本地 pinned build 的 41 个输出身份匹配；§273 四个精确锁定签名 NuGet 包的 canonical contentHash 与签名复核通过；§279 在本机重放 235/235 锁定制品 cache、210 artifact SPDX 字节证据、121-package SBOM freshness 和固定 SPDX 2.3 schema。§276 security scan 为 partial，不能外推为完整审查。字节/结构重放不确认许可适用性、notice 完整性、provenance、链接关系或再分发权限。2026-10-14 曾选择 MIT 作为候选；2026-10-15 用户无法确认原创贡献授权，故该候选已撤回。Win32Docs/SDK/WDK 生成输出适用性、完整 native provenance/linkage/notices、远端 CI 和 clean install 也仍开放。
- **§162 SPDX verifier baseline（当前全量元数据复核见 §172，PE 来源图见 §166）：** 41 个第三方包、210 个锁定制品、41 metadata、9 license、2 notice、1,149 supplemental member 已通过离线 verifier。286 个新补充成员是精确 artifact/path/size/SHA-256 身份记录；逐字节验证不表示每个文件都是许可证或其许可适用于项目。SBOM 仍为 121 packages/137 relationships，SPDX 2.3 schema 通过。所有 `licenseConcluded` 保持 `NOASSERTION`，许可适用性/再分发义务及所有者发行范围仍需审阅。
- **§279 当前本机离线重放：** 复现命令及全部摘要、计数、限制见 [`PROJECT_AUDIT_REPORT.md`](PROJECT_AUDIT_REPORT.md) §279。四项检查分别确认 42 packages/235 artifacts 的 lock cache、41 packages/210 artifacts/1,149 supplemental members 的 SPDX bytes、121 package records 的 freshness 和固定 SPDX 2.3 schema；当前 SBOM 有 137 relationships，121/121 个 package 的 `licenseConcluded` 均为 `NOASSERTION`。此为机器证据重放，不是法律/所有者审阅。
- **§172 全量制品 metadata 复核：** 离线核验 `uv.lock` 中 235/235 个制品（199 wheel、36 sdist，41 包），校验大小/SHA-256、METADATA/PKG-INFO 名称/版本/摘要及 wheel RECORD 行。44 条记录缺少 License 与 License-Expression 字段，涉及 colorama、editables、pathspec、ruff、tokenizers、trove-classifiers；不据此推断许可。Protobuf 7.36.2 的 sdist 使用 `BSD-3-Clause`，7 个 wheel 使用旧式 `3-Clause BSD License` 文本；SPDX evidence 仍采用 sdist 的有效表达式且未更改声明。机器证据 [`locked-wheel-metadata-audit.json`](locked-wheel-metadata-audit.json) SHA-256 为 `b1dbbf4bb7a636cebe11cee8017ffdecfaa6a57eeb8b73383537c63c80421b9c`，可由 `python scripts/verify_locked_wheel_metadata_audit.py --cache-dir <sha256-cache>` 离线复核。该元数据检查不决定许可证适用性；项目 LICENSE、发行范围、Tokenizers Rust/native provenance 与 notices 仍需所有者审阅。此前 §171 只覆盖 26 wheel，属于历史快照。
- 当前包配置的范围：项目运行依赖仍为空，PyAV 与 faster-whisper 属于 `asr` extra，Playwright 属于 `browser` extra，Ruff 与 `skills-ref` 属于 `dev` group；默认启用的 `build` group 锁定 Hatchling/editables，供源安装构建项目。若构建 Python wheel，仅包括 `src/douyin_transcript`。因此应把源 Skill 当前交付、Python 包可选依赖、默认构建工具和 dev 组分别审阅；未来把依赖或原生二进制并入产品时需要重新确定分发范围。
- 2026-10-11 本机复核（审计 §157）：现存证据可离线验证 41 个第三方包、94 个制品及 863 个补充成员；固定 SPDX 2.3 schema 通过，按记录时间重建的 SBOM 内容一致，NumPy 1,130 行原生成员清单与锁定哈希匹配。当时该缓存没有其余 141 个锁定 artifact；§159 已由独立私有缓存补齐全部锁定 artifact 的字节与摘要检查。两类字节检查都不证明 native 构建来源、链接关系或许可证适用性。项目 `LICENSE`、所有者发行范围决定、远端 CI 与干净安装仍未完成。
- 2026-10-11 Windows PE 导入补充（审计 §158）：新映射校验了 6/6 个锁定 Windows wheel 中的 20 个 PE 成员及 250 项普通/延迟 DLL 导入，所有成员摘要与 wheel `RECORD` 一致。该专用私有缓存另含 95,405,677 字节，不属于原 SPDX 缓存的 94/235 计数。导入表不能推出静态链接/运行时动态加载或许可证适用结论；细节及 JSONL 摘要见下方专节与审计 §158。
- 2026-10-11 更正后全锁定归档清点（审计 §161）：对 235/235 个锁定 sdist/wheel 逐件索引，共 86,827 个归档成员和 6,239 个名称/路径候选行；修复 ZIP 未设置 Unix 类型位时的 50 个文件类型误分类。正式清单、manifest 与固定 JSONL 分片见 [`artifact-member-inventory-complete.md`](artifact-member-inventory-complete.md)。
- **§161 候选成员哈希结果：** 1,160 个非空候选经精确 `(package, version, artifact SHA-256, path)` 对账后有 286 个未绑定普通文件，已全部流式哈希并加入 supplemental evidence。36 个包共 90 种不同内容 SHA-256；60 条与同包已有成员证据内容相同。清单按字节验证覆盖 210 个制品、1,149 个补充成员。§162 将 FlatBuffers 的旧 evidence_policy 歧义修正为与版本特定的 reviewed Apache-2.0 legacy mapping 一致；SBOM `licenseConcluded` 仍为 `NOASSERTION`。旧 §160 的 297 为粗略差额，已复算更正。它不是 286 项许可证结论；native/完整 BOM、构建来源、链接映射、许可适用性或发行批准仍未证明，`licenseConcluded=NOASSERTION`。
- **原生 WFP 计划工具范围：** `native/windows/wfp-policy-plan/packages.lock.json` 锁定 CsWin32 `0.3.360` 及 Win32Docs、Win32Metadata、WDK Win32Metadata 元数据包；它们是仅供审阅的策略计划工具的构建期依赖，不随当前应用交付，按当前 SBOM 范围不在应用 SBOM 中。独立 NuGet build-only 盘点见 [DOTNET_BUILD_DEPENDENCY_REVIEW.md](DOTNET_BUILD_DEPENDENCY_REVIEW.md) 与审核报告 §§199、209：§199 当时只核对本地摘要关系，签名验证随后已由 §209 对四个 lockfile 精确版本完成并通过。Win32Docs 包级许可条款、SDK/WDK 条款对生成输出的适用范围、独立下载重现和远端 CI 仍未闭合；签名验证不代表许可证或发行获批。

## 锁定依赖 SPDX 清单

- 运行 `python scripts/generate_spdx_sbom.py --lockfile skills/douyin-transcript/uv.lock --cache-dir <sha256-cache> --output docs/third-party-sbom.spdx.json` 可离线重建 SPDX 2.3 JSON。`--cache-dir` 必须包含清单所引用、以小写 SHA-256 命名的全部 artifact。
- **生成边界：** 生成器在写入前自行调用离线 verifier，并将同一份有界读取的 lock/evidence 字节同时传给校验器和 SPDX 构建过程；两者输入摘要不一致、证据字段或成员摘要与锁定 artifact 不符、缓存缺失、输入超过 16 MiB、证据超过 5,000 行或表达式超过 65,536 字符/4,096 tokens/64 层嵌套时失败关闭。文件打开时以 `lstat`/`fstat` 核对常规文件身份，并在可用平台启用 nonblocking/no-follow flags，避免 FIFO 和路径替换造成阻塞或错误读取。文件级 SPDX expression 和写入 `licenseComments` 的审阅说明均绑定到经审阅的包版本、制品类型/摘要、归档路径和文件摘要固定表；篡改表达式或说明文字会失败。失败不会创建输出文件。正式扫描的原始发现仍封存于 `PROJECT_AUDIT_REPORT.md` 第 48 节；本地整改和回归记录见第 49 节（CWE-400/345）。
- 当前清单包含 `uv.lock` 的 42 个包记录：`douyin-transcript` 本身 1 个、第三方组件 41 个；保留所有平台/Python 条件变体、`asr` 与 `browser` 可选依赖、默认构建组以及 dev 组。
- SPDX document namespace 由锁文件、许可证证据清单、生成器内容和创建时间共同生成，避免不同输入复用同一个标识。
- SPDX 的 42 个基础 `uv.lock` package/version records 与 `uv export --format cyclonedx1.5 --all-extras --all-groups --frozen` 对齐；此外，SBOM 增列 79 个由锁定 Playwright Windows x64 wheel sidecars 明确列出的 npm 包，因此整份 SPDX 有 121 个 package records、137 个 relationships（§91）。生成物通过 SPDX 上游 [support/2.3 JSON Schema](https://github.com/spdx/spdx-spec/blob/support/2.3/schemas/spdx-schema.json) 验证，schema SHA-256 `4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212`。CycloneDX 仅用于基础锁定依赖的交叉核对，不是 SPDX 产物。
- Schema 检查现在可重复运行：`scripts/schemas/spdx-2.3.schema.json` 固定为官方 `support/2.3` schema 的 SHA-256 `4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212`；`scripts/check_spdx_schema.py` 由独立 `tools/spdx-schema-check/uv.lock` 中的 `jsonschema==4.25.1` 驱动，并在 CI 校验提交的 SPDX JSON。该独立校验器仅供 CI 使用、不随应用交付，因此有意不纳入应用 SBOM；若 BOM 范围要覆盖整个仓库及 CI 工具链，需另行盘点并审查其许可证。校验器只检查 SPDX Schema 结构，不核实声明是否完整、制品字节是否存在或许可证适用性；不会推导 `licenseConcluded`。
- `uv.lock` 本身不保存许可证声明。独立证据清单把精确锁定发行物元数据中的有效 SPDX 作者表达式原样写入 `licenseDeclared`，允许由锁定发行物内哈希核对过的许可证文件支持声明，并为 FlatBuffers `25.12.19` 的精确旧式值记录了版本专属映射；当前 41 个锁定第三方 Python 发行包全部有 evidence-backed `licenseDeclared`。Playwright sidecar 另外列出 79 个去重 npm 组件，78 个有可识别许可证正文，1 个仅有 MIT 声明；所有记录均通过锁定 wheel/member 摘要固定，全部 `licenseConcluded` 仍为 `NOASSERTION`（§91）。`python-dateutil` 的 `Dual License` 元数据由精确锁定 sdist LICENSE 补证，采用 BSD-3-Clause 作为适用于全包代码的共同许可选项；editables、Pathspec、Trove Classifiers 的 wheel LICENSE 文件也绑定 artifact/member SHA-256。这些声明不表示许可证已获项目批准。

### 离线证据字节校验器

- 使用 `python scripts/verify_spdx_evidence.py --cache-dir <sha256-cache>` 校验当前锁文件和 `docs/third-party-license-evidence.json` 引用的发行物。缓存文件名必须是小写 64 位 SHA-256、不带扩展名。§161 当前证据清单引用 210 个唯一 artifact，并额外记录 1,149 个 supplemental license/notice-like 成员；§145 的历史快照为 94 个 artifact 和 863 个 supplemental 成员，§124 更早快照为 54 个 artifact 和 63 个 supplemental 成员。校验器会复核 lock URL、artifact SHA-256/大小、已列出的 metadata/license/notice/supplemental 成员及 79 个 npm 组件 sidecar/catalog 摘要。其余 archive 读取预算和 fail-closed 规则保持不变；该工具只核对已记录证据，不宣称完整枚举所有 native/bundled 组件。
- 校验器只读本地缓存，不联网、不安装依赖，也不把归档成员解压到磁盘。缺少任一已引用 artifact 或成员、artifact/hash/size 与 lock 不符、证据成员摘要不符时以非零状态退出。SHA-keyed cache 未提供时，不得把合成测试结果描述成真实证据已复核。
- 单元回归用合成 wheel 和 sdist 验证成功读取路径，并覆盖 metadata/license/notice/supplemental 摘要篡改、缺少成员、缓存 artifact 摘要错误、未锁定 artifact、tar/ZIP 与输入规模预算、ZIP 目录计数不一致、冲突成员身份及跨证据成员共享预算。初始校验阶段从证据清单记录的 `files.pythonhosted.org` HTTPS 锁定 URL 下载了 35 个归档到本机临时 SHA-keyed cache，合计 147,223,499 字节；后续 §64 加 8 个、§83 加 3 个、§87 加 7 个 Playwright wheel，并在 §89 加入 ONNX Runtime CPython 3.12 wheel，共 54 个 artifact。§124 的离线复核使用了这 54 个 artifact；§145 时清单已有 94 个 artifact 和 863 个 supplemental 成员，§159–161 后当前清单已扩展为 210 个 artifact 和 1,149 个 supplemental 成员。sidecar catalog 与 Schema 回归见审核报告 §91；只核对已记录成员，不证明完整 native/bundled BOM、适用性、`licenseConcluded` 或再分发义务。

### 2026-10-11 锁定 artifact 成员路径清点

- `scripts/inventory_locked_artifact_members.py` 对现有 SHA-256 命名缓存做离线成员清点，完整结果见 [`ARTIFACT_MEMBER_INVENTORY.md`](ARTIFACT_MEMBER_INVENTORY.md)，逐成员机器可读记录见 [`artifact-member-inventory.jsonl`](artifact-member-inventory.jsonl)。复现命令：`python scripts/inventory_locked_artifact_members.py --cache-dir <sha256-cache>`。
- 本节的 54 个缓存对象均与 `uv.lock` 中的精确 URL、包/版本、类型、SHA-256 和字节数匹配；该成员索引是 §145 NumPy 扩充前的快照，覆盖锁文件 235 个不同 artifact identity 中的缓存子集。索引了 31,403 个归档成员路径和声明大小，其中 196 个路径名命中许可证/通知关键词、62 个成员使用原生二进制后缀、36 个文件名命中原生依赖关键词、492 个成员名命中构建/依赖元数据规则。一个成员可带多个候选标签。
- 扫描仅读归档目录信息；不解压到磁盘、不下载或安装。候选标记依据路径名/后缀，不阅读或解释成员正文，也不核对各 wheel 的 `RECORD` 成员摘要；因此结果只是定位后续人工审阅的事实索引，不能证明完整组件 BOM、二进制链接关系、许可证适用性或构建来源。
- 本节记录的是当时 54 个 artifact 的成员路径快照，未包含 `uv.lock` 的其余 181 个制品。§159–161 后续验证了 235/235 个锁定 artifact 并完成归档成员索引，但本节旧快照的候选正文仍未因此自动成为许可审阅结论。发行范围仍由所有者决定，所有 `licenseConcluded` 继续为 `NOASSERTION`，本索引不构成发布批准。

### 当前 Windows 环境中的发行包元数据抽查

- 2026-10-10 的早期 Windows Python 3.11 元数据快照（构建/校验依赖加入前）检查了 33 个第三方锁记录，其中 32 个精确版本已安装；29 个包记录了 `License-Expression` 或旧式 `License` 字段。新增构建/校验包的锁定发行物证据另见 §64。
- 后续复核了这 32 个已安装发行包的 `dist-info/RECORD`：元数据路径中名称含 `license`、`notice` 或 `copying` 的 65 个候选文件均存在，且文件 SHA-256 与各自 RECORD 一致。该核对验证的是当前安装文件和其 RECORD 的内部一致性，不等同于锁定 wheel 文件哈希、逐份阅读许可证文本或法律结论。下表原样记录当前安装元数据的许可证字段及候选文件数，旧式自由文本未擅自转换为 SPDX 表达式。
- 未包含这些字段的三个已安装包是 Colorama 0.4.6、Ruff 0.14.14 和 Tokenizers 0.23.2。Colorama wheel 内含 BSD 3-Clause 的 `LICENSE.txt`，[PyPI 固定版本页](https://pypi.org/project/colorama/0.4.6/)的发行说明也指向 BSD 3-Clause；Ruff wheel 内含 MIT `LICENSE`，[Ruff v0.14.14 上游许可文件](https://github.com/astral-sh/ruff/blob/0.14.14/LICENSE)与之吻合；Tokenizers wheel 未提供 license 文件，但其 [v0.23.2 上游许可文件](https://github.com/huggingface/tokenizers/blob/v0.23.2/LICENSE)标注 Apache License 2.0。
- 未安装的唯一锁记录是 Python 3.12 条件下的 NumPy 2.5.3；当前环境中的 NumPy 2.4.6 元数据不能代替该版本的发行物核对。为检查锁定发行物，从 PyPI 读取了对应 CPython 3.12/Windows x86-64 wheel 到内存（未安装或保留），其 SHA-256 `0a59a421a32580a009e8a1751345bf829631b990dc1794b80514ab722b435def` 与 `uv.lock` 及 [PyPI 2.5.3 发行页](https://pypi.org/project/numpy/2.5.3/) 一致；wheel `METADATA` 声明 `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`。归档内有 20 个文件名含 `LICENSE`/`LICENCE`/`COPYING`/`NOTICE` 的条目。此检查只核对了锁定 Windows wheel 的哈希、声明和文件清单，没有逐份解释 bundled license 文本，也没有审查 macOS/Linux wheel；SPDX 仍为 `NOASSERTION`，不视为许可批准。
- 本机 `wsl.exe --status` 显示尚未安装 WSL 发行版，故 Linux/POSIX 实机复核仍不能在此工作区完成。

### 精确锁定发行物中的作者许可证声明

- 读取锁文件中的 33 个第三方发行物：有 sdist 的记录使用锁定 sdist；仅有 wheel 的记录使用与当前 Windows/Python 3.11 环境兼容的锁定 wheel。共读取 135,567,678 字节到内存，每个完整发行物 SHA-256 均与 `uv.lock` 相同，未安装或保留这些文件。
- 从每个发行物的 `PKG-INFO` 或 `.dist-info/METADATA` 读取包作者字段，并保存该元数据条目 SHA-256。`docs/third-party-license-evidence.json` 记录包版本、字段原值、锁定 artifact URL/hash/size 和元数据路径/hash；生成器会校验每项证据仍对应当前 `uv.lock`。
- 28 个作者字段本身是有效 SPDX 表达式，清单按原值填入 `licenseDeclared`，不做字符串相似度转换。随后从其他精确锁定发行物中核对出 Colorama `BSD-3-Clause`、ONNX Runtime `MIT`、Ruff `MIT` 和 Tokenizers `Apache-2.0` 的许可证文本，并将路径、完整 artifact 哈希/大小、文件哈希写入证据清单；ONNX 的 `ThirdPartyNotices.txt` 也记录了锁定 wheel 与文件哈希。FlatBuffers 的 `Apache 2.0` 旧式值现在通过单项、精确版本映射写为 `Apache-2.0`：固定 PyPI 版本页和上游同版本标签的 `setup.py` / `LICENSE` 为映射提供来源。该映射不把上游文件声称为 wheel 内文件，也不改变 `licenseConcluded`。
- 这轮对 sdist 优先，wheel 仅用于 lock 中没有 sdist 的包；它不覆盖所有平台 wheel 的元数据差异或二进制内容。Protobuf 的锁定 sdist `PKG-INFO` 使用 `BSD-3-Clause`，而当前安装 Windows wheel 的 `METADATA` 使用旧式 `3-Clause BSD License`；SPDX 声明来源明确限定为证据清单中列明的 sdist。
- SPDX 2.3 将作者声明与分析结论分开：`licenseDeclared` 反映包作者声明；`licenseConcluded` 仍全部为 `NOASSERTION`，直至审阅实际 license/notice 文件、原生/Cargo 依赖、平台构建和发行范围。这里不构成法律意见或二进制再分发批准。

#### FlatBuffers 25.12.19 上游标签许可证核对

- PyPI 的固定版本页将 `flatbuffers 25.12.19` 标为 Apache Software License（Apache 2.0），并列出 universal wheel 的 SHA-256 `7634f50c427838bb021c2d66a3d1168e9d199b0607e6329399f04846d42e20b4`，与 `uv.lock` 一致。
- 上游 `google/flatbuffers` 的 `v25.12.19` 标签中，`python/setup.py` 明确写出版本 `25.12.19` 和旧式 `license='Apache 2.0'`；同一标签的 `LICENSE` 为 Apache License 2.0。可核对 [固定版本 setup.py](https://github.com/google/flatbuffers/blob/v25.12.19/python/setup.py)、[固定版本 LICENSE](https://github.com/google/flatbuffers/blob/v25.12.19/LICENSE) 和 [PyPI 固定版本页](https://pypi.org/project/flatbuffers/25.12.19/)。
- **映射边界：** 固定版本 PyPI 页将被锁 artifact 对应版本标为 Apache Software License，锁定 wheel 元数据中的精确 `License` 值为 `Apache 2.0`；同版本标签的 `setup.py` 保留该值，标签 `LICENSE` 对应 Apache License 2.0。生成器只对该包名/版本、metadata SHA-256、artifact SHA-256、字段和值及上述三条来源的完整组合接受 `Apache-2.0` 映射，并有负向回归拒绝改动后的值。标签文件不在锁定 wheel 中，也没有构建证明把该 wheel 绑定到 Git 标签，因此不会将标签文件记录为 wheel 内容或据此得出 `licenseConcluded`。所有 `licenseConcluded` 仍为 `NOASSERTION`。

### 精确锁定发行物许可证文件补查

从 `uv.lock` 对应发行物中提取以下文件，完整发行物哈希和大小先与锁文件核对；许可证文件哈希保存在 `docs/third-party-license-evidence.json`，生成器会拒绝未被当前锁文件固定的 artifact。证据使用锁定的平台 wheel 或 sdist。

| 锁定包/版本 | 发行物许可证文件 | 文件 SHA-256 | `licenseDeclared` | 尚未得出的结论 |
|---|---|---|---|---|
| Colorama `0.4.6` | `colorama-0.4.6.dist-info/licenses/LICENSE.txt`，wheel SHA-256 `4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6` | `cac35c02686e5d04a5a7140bfb3b36e73aed496656e891102e428886d7930318` | `BSD-3-Clause` | 此声明只描述包许可证，不评估整份应用的分发义务。 |
| editables `0.5` | `editables-0.5.dist-info/LICENSE.txt`，wheel SHA-256 `61e5ffa82629e0d8bfe09bc44a07db3c1ab8ed1ce78a6980732870f19b5e7d4c` | `c73e08a04e1557fdb49525fb7a579f73bcab84a254910b9350ee56daf143932d` | `MIT` | 该声明描述 editables；不推断构建工具链或整个项目的发行义务。 |
| Pathspec `1.1.1` | `pathspec-1.1.1.dist-info/licenses/LICENSE`，wheel SHA-256 `a00ce642f577bf7f473932318056212bc4f8bfdf53128c78bbd5af0b9b20b189` | `fab3dd6bdab226f1c08630b1dd917e11fcb4ec5e1e020e2c16f83a0a13863e85` | `MPL-2.0` | 该声明描述 Pathspec；不推断 dev 组其他组件的许可证或分发义务。 |
| ONNX Runtime `1.30.0` | `onnxruntime/LICENSE`，Windows CPython 3.11 wheel SHA-256 `0edd0145a6e3fce8a1276491dc784d615e3c58bcb952c9b4e5c876d5c6a12ad7` | `c250d6278f0b47a6439fb7592b08b58a55eb9f535aa49a1db63211c3f982b674` | `MIT` | 同 wheel 的 `onnxruntime/ThirdPartyNotices.txt` 为 344,457 字节、SHA-256 `c53a76501ef60db6f865f20599f220761201ac4057683acefdab37d861b86622`；组件尚未映射到链接二进制。 |
| Ruff `0.14.14` | `ruff-0.14.14.dist-info/licenses/LICENSE`，Windows x64 wheel SHA-256 `3dde1435e6b6fe5b66506c1dff67a421d0b7f6488d466f651c07f4cab3bf20fd` | `2597d854122b77ddc71971564ca2350a37608575ce324adc5650a2b2051c8f18` | `MIT` | Rust 依赖许可证/notice 尚未逐项核对。 |
| Trove Classifiers `2026.9.21.13` | `trove_classifiers-2026.9.21.13.dist-info/licenses/LICENSE`，wheel SHA-256 `8b1ff4f9c191b1040b71c37f1e445ab99732911e3cd91de52838453a854d7a17` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` | `Apache-2.0` | 该声明描述 Trove Classifiers；不推断 dev 组其他组件的许可证或分发义务。 |
| Tokenizers `0.23.2` | `tokenizers-0.23.2/tokenizers/LICENSE`，锁定 sdist SHA-256 `7f0f085686b9de0d0079e6f874ae053600db64c5d13049e0bbc0119926d25aac` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` | `Apache-2.0` | Rust 依赖许可证/notice 及构建 wheel 随附材料仍待核查。 |

以上七个锁定包的声明由 wheel/sdist 内许可证文件支持；没有调整 SPDX `licenseConcluded`。FlatBuffers 声明另由固定元数据和单项审阅映射支持。ONNX Runtime 二进制依赖、其他平台 wheel、PyAV/FFmpeg 和最终交付范围仍需逐项审阅。

#### ONNX Runtime 1.30.0 锁定 wheel 的 notice 内容抽查

本次从锁定 CPython 3.11/Windows x64 wheel（14,309,136 字节，SHA-256 `0edd0145a6e3fce8a1276491dc784d615e3c58bcb952c9b4e5c876d5c6a12ad7`）重新读取 `onnxruntime/ThirdPartyNotices.txt`；文件为 344,457 字节、6,369 行，SHA-256 `c53a76501ef60db6f865f20599f220761201ac4057683acefdab37d861b86622`。同一 wheel 的二进制文件清单包括 `onnxruntime.dll`、`onnxruntime_providers_shared.dll` 和 `onnxruntime_pybind11_state.pyd`。

- notice 含 Intel Math Kernel Library 的 Intel Simplified Software License。其文字列出再分发时保留版权/许可条款、不得未经许可借 Intel 名称背书，并明确禁止 reverse engineering、decompilation 和 disassembly。对最终交付的实际适用范围仍需核实；wheel 中未观察到独立 MKL DLL，这不能排除静态链接或其他组件关系。
- 本机锁定 wheel notice 的既有检查记录了 Mbed TLS 条款，条文随后说明该发行使用 Apache-2.0。后续从 Microsoft `v1.30.0` 官方标签读取原始 [ThirdPartyNotices.txt](https://github.com/microsoft/onnxruntime/blob/v1.30.0/ThirdPartyNotices.txt) 并与项目锁定环境中的同版本 notice 比较：两份文件都含 Intel MKL 与 Mbed TLS，6370 行文本在将 CRLF 统一为 LF 后完全相同；大小分别为 344,457 与 338,088 字节、SHA-256 分别为 `c53a76501ef60db6f865f20599f220761201ac4057683acefdab37d861b86622` 和 `143764b952fdb1a7c69ce653bfba74a7744d6a8a573bfb73e235fba356c83de3`。这确认的是文本一致性，不是 notice 条目到 wheel 链接二进制的映射。
- notice 的内容是第三方归属材料，不是本轮二进制链接映射。仍需将相关条目与目标 Windows wheel 的实际构建/链接组件对应，并审阅所有需要随产品交付的文本和源代码材料。

因此，ONNX Runtime 的包级 `licenseDeclared=MIT` 有 wheel 内 `onnxruntime/LICENSE` 文件证据；整个 wheel 的 `licenseConcluded` 仍为 `NOASSERTION`。该文件不是本仓库的项目许可证，当前仓库根目录尚无 `LICENSE`。以上为发行物内容抽查，不构成法律结论或再分发批准。

| 锁定包/版本 | 安装元数据 `License-Expression` 或 `License` 原值 | RECORD 中候选路径数 |
|---|---|---:|
| [anyio](https://pypi.org/project/anyio/4.15.1/) `4.15.1` | `MIT` | 1 |
| [av](https://pypi.org/project/av/15.1.0/) `15.1.0` | `BSD-3-Clause` | 3 |
| [certifi](https://pypi.org/project/certifi/2026.7.22/) `2026.7.22` | `MPL-2.0` | 1 |
| [click](https://pypi.org/project/click/8.5.0/) `8.5.0` | `BSD-3-Clause` | 1 |
| [colorama](https://pypi.org/project/colorama/0.4.6/) `0.4.6` | 无该字段 | 1 |
| [ctranslate2](https://pypi.org/project/ctranslate2/4.8.2/) `4.8.2` | `MIT` | 0 |
| [faster-whisper](https://pypi.org/project/faster-whisper/1.2.1/) `1.2.1` | `MIT` | 1 |
| [filelock](https://pypi.org/project/filelock/4.0.12/) `4.0.12` | `MIT` | 1 |
| [flatbuffers](https://pypi.org/project/flatbuffers/25.12.19/) `25.12.19` | `Apache 2.0`（旧式字段） | 0 |
| [fsspec](https://pypi.org/project/fsspec/2026.9.0/) `2026.9.0` | `BSD-3-Clause` | 1 |
| [greenlet](https://pypi.org/project/greenlet/3.5.6/) `3.5.6` | `MIT AND PSF-2.0` | 2 |
| [h11](https://pypi.org/project/h11/0.16.0/) `0.16.0` | `MIT` | 1 |
| [hf-xet](https://pypi.org/project/hf-xet/1.7.0/) `1.7.0` | `Apache-2.0` | 1 |
| [httpcore](https://pypi.org/project/httpcore/1.0.9/) `1.0.9` | `BSD-3-Clause` | 1 |
| [httpx](https://pypi.org/project/httpx/0.28.1/) `0.28.1` | `BSD-3-Clause` | 1 |
| [huggingface-hub](https://pypi.org/project/huggingface-hub/1.33.0/) `1.33.0` | `Apache-2.0` | 1 |
| [idna](https://pypi.org/project/idna/3.20/) `3.20` | `BSD-3-Clause` | 1 |
| [iniconfig](https://pypi.org/project/iniconfig/2.3.1/) `2.3.1` | `MIT` | 1 |
| [numpy](https://pypi.org/project/numpy/2.4.6/) `2.4.6` | `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` | 20 |
| [onnxruntime](https://pypi.org/project/onnxruntime/1.30.0/) `1.30.0` | `MIT License`（旧式字段） | 2 |
| [packaging](https://pypi.org/project/packaging/26.3/) `26.3` | `Apache-2.0 OR BSD-2-Clause` | 5 |
| [playwright](https://pypi.org/project/playwright/1.63.0/) `1.63.0` | `Apache-2.0` | 8 |
| [pluggy](https://pypi.org/project/pluggy/1.6.0/) `1.6.0` | `MIT` | 1 |
| [protobuf](https://pypi.org/project/protobuf/7.36.2/) `7.36.2` | `3-Clause BSD License`（旧式字段） | 1 |
| [pyee](https://pypi.org/project/pyee/13.0.1/) `13.0.1` | `MIT` | 1 |
| [Pygments](https://pypi.org/project/pygments/2.21.0/) `2.21.0` | `BSD-2-Clause` | 2 |
| [pytest](https://pypi.org/project/pytest/8.4.2/) `8.4.2` | `MIT` | 2 |
| [PyYAML](https://pypi.org/project/pyyaml/6.0.3/) `6.0.3` | `MIT` | 1 |
| [ruff](https://pypi.org/project/ruff/0.14.14/) `0.14.14` | 无该字段 | 1 |
| [tokenizers](https://pypi.org/project/tokenizers/0.23.2/) `0.23.2` | 无该字段 | 0 |
| [tqdm](https://pypi.org/project/tqdm/4.70.1/) `4.70.1` | `MPL-2.0 AND MIT` | 1 |
| [typing-extensions](https://pypi.org/project/typing-extensions/4.16.0/) `4.16.0` | `PSF-2.0` | 1 |

Python 3.12 条件下另有 NumPy `2.5.3` 锁记录，该版本未安装在此 Python 3.11 环境；对应 Windows x86-64 wheel 的锁定 SHA-256 和元数据检查见上文。此表覆盖安装元数据盘点，不代表全部 33 个第三方锁记录的上游源文件、所有平台 wheel 或捆绑组件均已审阅。

对上述 32 个精确安装版本逐一查询 PyPI 固定版本 JSON API 后，29 个带 License 字段的值在忽略大小写/空白差异后与安装 `METADATA` 相符；Colorama、Ruff、Tokenizers 的发行元数据未提供该字段，其他上游证据见上文五 wheel 表及 Colorama/Tokenizers 来源链接。该核对确认发布元数据来源一致，不代替对许可证文本、第三方依赖和平台 wheel 的审查。

### 五个重点锁定 Windows wheel 的补查

以下发行物均按 `uv.lock` 固定的文件 URL 读取到内存，并逐个核对 SHA-256；没有安装或保留 wheel。表中“上游声明”是项目/发行页提供的许可证据，“wheel 观察”只记录 ZIP 文件清单，不据此推断二进制许可完整性。

| 锁定发行物 | 上游声明 | 锁定 Windows wheel 观察 | 未决复核 |
|---|---|---|---|
| CTranslate2 `4.8.2` | [PyPI 固定版本页](https://pypi.org/project/ctranslate2/4.8.2/) 标为 MIT；[v4.8.2 上游 LICENSE](https://github.com/OpenNMT/CTranslate2/blob/v4.8.2/LICENSE) 为 MIT。 | wheel SHA-256 与锁文件一致；ZIP 中未见 license/notice/COPYING 路径，包含 `ctranslate2.dll`、`cudnn64_9.dll`、`libiomp5md.dll` 和 `_ext.pyd`。 | DLL/原生依赖的来源、精确版本及许可/notice 尚未逐项核实，特别是 cuDNN 与 Intel OpenMP；不能仅凭 CTranslate2 的 MIT 声明批准 wheel 再分发。 |
| FlatBuffers `25.12.19` | [PyPI 固定版本页](https://pypi.org/project/flatbuffers/25.12.19/) 声明 Apache 2.0；[v25.12.19 上游 LICENSE](https://github.com/google/flatbuffers/blob/v25.12.19/LICENSE) 为 Apache-2.0。 | wheel SHA-256 与锁文件一致；ZIP 中未见 license/notice 路径或原生二进制。 | 锁定 wheel 未携带许可证/notice 文件；若要再分发该 wheel 或将其纳入打包交付，需确认并提供所需文本。 |
| ONNX Runtime `1.30.0` | [PyPI 固定版本页](https://pypi.org/project/onnxruntime/1.30.0/) 展示 MIT；[v1.30.0 上游 LICENSE](https://github.com/microsoft/onnxruntime/blob/v1.30.0/LICENSE) 为 MIT，并提供[固定版本 ThirdPartyNotices.txt](https://github.com/microsoft/onnxruntime/blob/v1.30.0/ThirdPartyNotices.txt)。 | CPython 3.11/Windows x64 wheel 为 14,309,136 字节，SHA-256 `0edd0145a6e3fce8a1276491dc784d615e3c58bcb952c9b4e5c876d5c6a12ad7` 与 `uv.lock` 一致；ZIP 包含 `onnxruntime/ThirdPartyNotices.txt`（344,457 字节，SHA-256 `c53a76501ef60db6f865f20599f220761201ac4057683acefdab37d861b86622`）。安装目录对应文件也与 RECORD 的 SHA-256/大小一致。 | notice 条款已在主审核报告第 26 节抽查，识别出 Intel MKL 和 Mbed TLS 的许可说明；仍待把 notice 条目映射到具体链接组件、核实构建覆盖范围并检查其他平台 wheel。不能仅依据 ONNX Runtime 包级 MIT 声明推断整个 wheel 的二进制结论。 |
| Tokenizers `0.23.2` | [PyPI 固定版本页](https://pypi.org/project/tokenizers/0.23.2/) 有 Apache Software License classifier；[v0.23.2 上游 LICENSE](https://github.com/huggingface/tokenizers/blob/v0.23.2/LICENSE) 为 Apache-2.0。 | wheel SHA-256 与锁文件一致；ZIP 中未见 license/notice/COPYING 路径，包含 `tokenizers/tokenizers.pyd`。 | Rust 扩展打包的 Cargo 子依赖及其 attribution/notice 要求尚未逐项核实；上游根 LICENSE 不证明 wheel 已携带完整第三方 notices。 |
| Ruff `0.14.14` | [PyPI 固定版本页](https://pypi.org/project/ruff/0.14.14/) 标为 MIT 并列出 `LICENSE`；[v0.14.14 上游 LICENSE](https://github.com/astral-sh/ruff/blob/0.14.14/LICENSE) 与 [Cargo.toml](https://github.com/astral-sh/ruff/blob/0.14.14/Cargo.toml) 均指向 MIT。 | wheel SHA-256 与锁文件一致；包含 `ruff-0.14.14.dist-info/licenses/LICENSE`，另有编译的 Rust 程序。 | Cargo 依赖的完整许可/notice 仍未核实；还需确认 dev 工具是否进入最终发行交付范围。 |

这些检查补充了精确版本的来源和 wheel 文件观察，但不替代逐项审阅第三方组件、notice、目标平台构建配置或发行形态。尤其 CTranslate2、ONNX Runtime、Tokenizers、Ruff 的原生/捆绑组件仍有未决项；FlatBuffers 的 `licenseDeclared` 现由精确元数据和审阅映射记录，所有 `licenseConcluded` 仍为 `NOASSERTION`，本节不构成二进制分发批准。

### 固定版本上游来源对照（2026-10-09）

- CTranslate2 v4.8.2 的[上游安装/构建文档](https://github.com/OpenNMT/CTranslate2/blob/v4.8.2/docs/installation.md)说明可配置 Intel OpenMP、cuDNN、MKL 等构建后端；这些是源码构建选项，不是 PyPI wheel 的构建清单。需取得与锁定 wheel SHA-256 绑定的 build manifest/native dependency inventory，逐项记录 DLL 来源、精确版本、链接方式及 notices。
- ONNX Runtime v1.30.0 上游 [`ThirdPartyNotices.txt`](https://github.com/microsoft/onnxruntime/blob/v1.30.0/ThirdPartyNotices.txt)与项目锁定环境中的同版本安装文件都含 Intel MKL 与 Mbed TLS。原始文件大小/SHA-256 分别为 338,088 / `143764b952fdb1a7c69ce653bfba74a7744d6a8a573bfb73e235fba356c83de3` 和 344,457 / `c53a76501ef60db6f865f20599f220761201ac4057683acefdab37d861b86622`；两者 6370 行文本在 CRLF/LF 统一后完全相同，字节差异来自换行格式。该核对消除了先前误报的内容差异；notice 条目与 wheel 实际链接二进制的关系仍未映射，也未改变 SPDX `licenseConcluded`。
- Tokenizers v0.23.2 的上游 [`tokenizers/Cargo.toml`](https://github.com/huggingface/tokenizers/blob/v0.23.2/tokenizers/Cargo.toml)声明 Apache-2.0、列出 Rust 依赖，并排除 `Cargo.lock`；该源清单不能证明发布 wheel 的实际 resolved dependency graph。需要针对锁定 wheel 的构建来源提供 Cargo lockfile/SBOM 与随包 notice 记录。
- Ruff v0.14.14 上游 [`Cargo.toml`](https://github.com/astral-sh/ruff/blob/0.14.14/Cargo.toml)声明 MIT，固定版本 [`LICENSE`](https://github.com/astral-sh/ruff/blob/0.14.14/LICENSE)还包含外部维护库的归属材料；wheel 中虽有 `LICENSE`，仍需核对其字节与标签文件一致，并检查 wheel 对应 Rust 依赖的 license/notice。由于 Ruff 当前只在 dev group，所有者应先确定 dev tooling 是否进入将来交付物范围。
- PyAV v15.1.0 的 [`pyproject.toml`](https://github.com/PyAV-Org/PyAV/blob/v15.1.0/pyproject.toml)声明 BSD-3-Clause；同标签的 [`scripts/build-deps`](https://github.com/PyAV-Org/PyAV/blob/v15.1.0/scripts/build-deps)中出现 `--enable-gpl` 和 `--enable-libx264`。该 helper 是上游源码构建线索，不能证明 PyPI wheel 使用相同 FFmpeg 配置。FFmpeg 官方[许可说明](https://ffmpeg.org/legal.html)将默认 LGPL 与可选 GPL 组件区分，并点名 libx264；需逐个目标平台取得与 wheel 哈希绑定的 FFmpeg 版本、configure 参数、组件/notice 清单和源码对应关系，再评估交付范围。

### 安装环境许可证/notice 文件清点（2026-10-10）

- 在当前 Windows/Python 3.11 项目的 32 个锁定第三方安装包中，按 `dist-info/RECORD` 列出路径名含 `license`、`notice` 或 `copying` 的 65 个候选文件；65 个均存在，SHA-256 与对应 RECORD 项一致。此结论限于当前安装目录，并未与每个 wheel/sdist 整体哈希独立比较。
- 文件名筛选有已知边界：会包含 `AUTHORS` 等非许可证材料和 `packaging/licenses/` 下的 Python 源文件；也可能漏掉名称不含筛选词但仍承载义务的文件。该数量是候选清点，不是完整 notice 覆盖率。
- Playwright 1.63.0 的安装内容中观察到 Node driver、`ThirdPartyNotices.txt` 及多份内嵌组件许可证；NumPy 2.4.6 安装内容含多份 vendored 组件许可文本。应将这些材料纳入对应安装发行物的组件追踪；当前仍没有与 wheel 构建来源绑定的完整 BOM/依赖图或各组件适用范围结论。
- 其他检查边界：CTranslate2 4.8.2、FlatBuffers 25.12.19、Tokenizers 0.23.2 的本机安装元数据中未找到文件名筛选出的 license/notice 候选路径；这不证明上游发行物没有相关义务。Python 3.12 的 NumPy 2.5.3 和 macOS/Linux wheel 不在此安装目录清点范围内。所有 `licenseConcluded` 继续为 `NOASSERTION`，项目发行决定仍未完成。

以上均为固定版本上游文本与已记录 wheel 内容的技术对照，不是制品构建证明或法律结论；不更改现有 `licenseDeclared` / `licenseConcluded`。

## 已核对的组件

| 组件 | 当前锁定版本或来源 | 上游声明 | 发行边界与未决事项 |
|---|---|---|---|
| faster-whisper | `1.2.1` | MIT；见 [v1.2.1 LICENSE](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/LICENSE) | 当前项目通过可选 `asr` extra 安装，仓库不包含其 wheel |
| Medium ASR 模型 | `Systran/faster-whisper-medium`，revision `08e178d48790749d25932bbc082711ddcfdfbc4f` | 固定 Hugging Face revision 页面声明 MIT；见[模型文件页](https://huggingface.co/Systran/faster-whisper-medium/tree/08e178d48790749d25932bbc082711ddcfdfbc4f) | setup 在用户本机下载模型；仓库不包含权重。该声明对应上游模型仓库，不是本项目的许可证 |
| Playwright Python | 锁文件当前解析 `1.63.0` | Apache-2.0；见 [v1.63.0 pyproject](https://github.com/microsoft/playwright-python/blob/v1.63.0/pyproject.toml) | 项目通过可选 `browser` extra 安装 Python 包；Playwright 文档说明浏览器二进制需另行安装，默认 Chromium 是其支持的开源构建，存放在本机缓存；当前仓库不包含浏览器文件。见[浏览器安装说明](https://playwright.dev/python/docs/browsers) |
| PyAV | `15.1.0` | PyAV 源码许可证为 BSD-3-Clause；见 [v15.1.0 LICENSE](https://github.com/PyAV-Org/PyAV/blob/v15.1.0/LICENSE.txt) 和 [PyPI 15.1.0 元数据](https://pypi.org/project/av/15.1.0/) | Windows wheel 曾在仓库外临时环境安装用于 SEC-31 动态验证；未随仓库分发。2026-10-10 已将 14 个锁定 CPython 3.11/3.12 Windows/macOS/Linux wheel 与 `uv.lock` 核对哈希，均观察到 FFmpeg 7.1.1、x264/x265 库和 libx264/libx265 构建字符串。各 wheel 的完整 configure/build provenance、组件 notice/源码和许可适用范围仍未确认。不能仅凭 PyAV 的 BSD-3-Clause 标签判断所含二进制的义务 |

## 发布风险与对策

1. **PyAV wheel 的 FFmpeg 组件仍需按目标平台核对。** FFmpeg 官方说明默认许可为 LGPL-2.1-or-later，组合 libx264/libx265 等 GPL 库会要求采用对应 GPL 构建；二进制再分发也需要准确的源码、配置和 notice 材料，见 [FFmpeg legal considerations](https://ffmpeg.org/legal.html)。14 个锁定 Windows/macOS/Linux wheel 已核对哈希并观察到 x264/x265 库和构建字符串；尚未取得完整 build configuration/provenance，也未确认组件 notice/源码材料或适用许可例外。在这些事项核清前，不把 PyAV wheel 或包含它的二进制包纳入本项目发行。此观察不证明当前源代码树违法，也不构成法律意见。
2. **模型和浏览器不可并入本项目许可证。** 若未来将模型权重、Playwright 浏览器、PyAV wheel 或其 FFmpeg 动态库打进可执行包，需分别保留相应版权/许可文本，并按目标平台的实际二进制完成源代码与构建配置审查。当前源代码目录不打包这些二进制。
3. **项目自身许可证仍待所有者选择。** 由仓库所有者决定适用于本项目代码的许可证，并新增对应 `LICENSE`；本复核不替所有者选 MIT、Apache-2.0 或其他许可证。
4. **完成完整锁定依赖清单。** SPDX 组件/版本盘点已从 `uv.lock` 生成并校验；逐项确认直接与传递依赖的许可证及 notice 文件仍未完成。对每种支持平台的 PyAV wheel 还需保存 FFmpeg 版本、编译配置、组件清单及上游要求的源码/notice。

## 当前状态

- 上游代码、模型和浏览器 Python 包的初步许可证来源已记录。
- SPDX 传递依赖清单已覆盖 42 个 `uv.lock` records 和 79 个 Playwright sidecar npm package records。早期已安装包快照中的 32 个发行包 RECORD 有 65 个 license/notice 候选文件，均存在且内部 SHA-256 一致；§162 离线 verifier 对 41 个锁定第三方 Python 发行物核验 210 个 artifact、41 个 metadata、9 个 license、2 个 notice 和 1,149 个 supplemental 成员；§166 的 PE import map 扩大到全部 40 个 Windows wheel。所有 41 个锁定第三方包有 evidence-backed `licenseDeclared`；另 79 个 npm 条目中 78 个有可识别许可证正文、1 个仅有声明（§91）。Playwright 8 个锁定平台 wheel 的 64 个候选文件与 RECORD 一致（§87）。逐项审查所有 bundled 文本、PyAV wheel 内 FFmpeg 配置/notice 和发行范围仍未完成。121 个 SBOM package record 的 `licenseConcluded` 均为 `NOASSERTION`；项目 LICENSE 与二进制再分发审查也未完成。
- 在上述事项关闭前，P6 仍为 **NOT READY**。

## 2026-10-10 ONNX Runtime CPython 3.12 Windows wheel notice 补证

- `onnxruntime==1.30.0` 的锁定 CPython 3.12/Windows x64 wheel 大小为 14,311,470 bytes，SHA-256 `f3501472571f1b1eee50e017851e7929f5ea37312d2d8c2494a19e8fc58b4a38`。其中 `onnxruntime/ThirdPartyNotices.txt` 为 344,457 bytes，SHA-256 `c53a76501ef60db6f865f20599f220761201ac4057683acefdab37d861b86622`，并与 wheel `RECORD` 相符；该内容与 CPython 3.11 wheel 的 notice 相同。
- 本节记录时，离线 verifier 核验 41 packages、54 artifacts、41 metadata、9 license、2 notice、63 supplemental members。新增引用只证明锁定归档中存在这些 notice 字节，不证明每项 notice 映射到实际链接二进制或满足所有再分发要求；所有 `licenseConcluded` 仍为 `NOASSERTION`，完整边界见项目审核报告 §89。NumPy wheel 补证后的当前计数见 §145。

## 2026-10-10 Playwright npm sidecar 组件证据与 SPDX 补充

- 对锁定 Playwright 1.63.0 Windows x64 wheel 的 `serverRegistry.js.LICENSE`（2,982 bytes，SHA-256 `3098a6efcbc11752cbdf6075fa65480f5470f78c8d981fab9c0796dc9a41cefe`）和 `utilsBundle.js.LICENSE`（106,591 bytes，SHA-256 `2495f30be29620d54b58339821eda0ebabdfb6ee9b09455f7285a06fd46fb9f3`）解析 sidecar 内 package@version 与许可证文本。两份成员均来自 wheel SHA-256 `2f9a707a6c6c91157ed77bff2b8caeb04b3c8d46e70d585fc134298cbe4b5cc6`，并与 ZIP `RECORD` 相符；组件清单、证据路径及 digest 固定于 `docs/third-party-license-evidence.json`。
- sidecar 共列出 81 次记录，去重后 79 个 npm package@version。78 个有可识别的许可证正文：MIT 65、ISC 7、BSD-3-Clause 4、BSD-2-Clause 1、BlueOak-1.0.0 1。`proxy-agent-negotiate@1.1.0` 只标示 MIT、没有正文；SBOM 将依据标为 sidecar declaration only，并保持 `licenseConcluded=NOASSERTION`。
- SBOM 为 79 个组件各建一个 package record，并从 Playwright 包建立 79 条 `CONTAINS`。不同 sidecar 中重复出现的组件会合并为一个版本记录并保留两个证据链接。`webp_codec.LICENSE` 无版本信息的 libwebp/Emscripten 内容仅留作范围注释；不生成无版本组件记录，也不把 Node.js/musl 文本推断为当前 Windows wheel 直接依赖。此清单确认 sidecar 中可见的内联 JavaScript 归属，不是 Playwright 全部 native/bundled BOM。
- 当前 SBOM 包括 42 个 `uv.lock` package records 加 79 个 npm package records，共 **121 packages / 137 relationships**。使用官方 SPDX `support/2.3` JSON Schema，SHA-256 `4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212`；临时 `jsonschema==4.25.1` 验证通过。两份 SPDX 测试共 **60 passed, 3 skipped**；Ruff 通过。锁定 artifact verifier 输出 **41 lock packages, 54 artifacts, 41 metadata, 9 license, 2 notice, 63 supplemental members**。
- 本次扩展不判定许可证适用性、兼容性、再分发义务或实际运行时使用范围。Playwright 另行下载的 Chromium 不在 Python wheel 组件快照中；项目自身许可证、所有 `licenseConcluded`、ONNX 到链接二进制映射、CTranslate2/Tokenizers/Ruff/PyAV 原生构建材料与远端 CI 仍开放，P6 仍为 **NOT READY**。

## 2026-10-14 `proxy-agent-negotiate@1.1.0` provenance metadata check

- The exact upstream [`packages/negotiate/package.json`](https://github.com/TooTallNate/proxy-agents/blob/b7e5f7ccce1a3ac5b339cc4c587974e8989cbc16/packages/negotiate/package.json) declares MIT. A read-only check of npm registry metadata found two attestations (npm publish and SLSA provenance). The provenance subject SHA-512 matches the registry tarball integrity; its source commit is [`b7e5f7ccce1a3ac5b339cc4c587974e8989cbc16`](https://github.com/TooTallNate/proxy-agents/commit/b7e5f7ccce1a3ac5b339cc4c587974e8989cbc16), and the response includes a transparency-log inclusion proof. GitHub reports the exact source commit signature as verified. The commit tree has no root or package-level LICENSE/NOTICE file.
- This is registry metadata inspection, not local Sigstore verification. The exact tarball is not in the local npm cache, so its recorded SHA-256 was not recomputed. The DSSE certificate and transparency-log proof have not been independently verified locally; keep `licenseDeclared=MIT` and `licenseConcluded=NOASSERTION`, and do not treat provenance metadata as a license text or conclusion. npm documents `npm audit signatures` as the package verification path ([provenance verification](https://docs.npmjs.com/viewing-package-provenance/), [audit signature bundles](https://docs.npmjs.com/cli/commands/npm-audit/)); that command was not run because the documented prerequisite is an installed dependency tree.

## PyAV 15.1.0 跨平台 wheel 复核（2026-10-10）

- 对应 `uv.lock` 的 14 个 PyPI wheel 覆盖 CPython 3.11/3.12 与 Windows、macOS、Linux；14 个 artifact 的 SHA-256 均匹配锁文件。wheel 中均观察到 FFmpeg 7.1.1 标识、x264/x265 原生库和 `--enable-libx264` / `--enable-libx265` 配置字符串。PyAV `LICENSE.txt` 存在，内容与上游 v15.1.0 许可证一致；PyPI 元数据声明 BSD-3-Clause。
- 这批 wheel 没有 Trusted Publishing provenance，因此无法仅凭下载 artifact 与上游源码版本建立完整构建来源链。2026-10-13 的 RECORD 校验清点补出了 wheel 内可读 configure 字符串，但嵌入字符串不等于发布方签署的完整构建清单，也不证明没有其他 GPL 组件、适用例外或其他许可义务。PyAV v15.1.0 上游 build helper 默认使用 FFmpeg 8.0，且 helper 配置与 wheel 可见的 FFmpeg 7.1.1/x265 证据不同，不能作为 wheel 的构建清单。
- **后续动作：** 所有者先确定实际发行范围；对每个拟分发平台索取与 artifact hash 绑定的 FFmpeg build manifest、完整 configure 参数、组件 BOM、license/notice 与对应源码，再由适格人员审查义务。此前“其他平台 wheel 未检查”的表述应理解为尚未完成构建/许可结论，而不是未读取 wheel。SPDX `licenseConcluded` 继续全部为 `NOASSERTION`；不批准 PyAV/native binary 再分发，P6 仍为 **NOT READY**。

## PyAV 15.1.0 锁定 wheel 中 FFmpeg configure 字符串清点（2026-10-13）

- 新增离线脚本 [`inventory_pyav_ffmpeg_build_config.py`](../scripts/inventory_pyav_ffmpeg_build_config.py) 和机器可读结果 [`pyav-ffmpeg-build-config-inventory.json`](pyav-ffmpeg-build-config-inventory.json)。输入限定为 `uv.lock` 中 `av==15.1.0` 的 14 个 wheel；每个压缩 artifact 的 SHA-256/大小与锁文件匹配，扫描不联网、不安装、不执行 wheel，也不向磁盘解压成员。
- 14/14 wheel 都找到可读 FFmpeg configure 字符串；共记录 98 个原生成员（每个 wheel 7 个），每一项均绑定成员路径、大小、SHA-256，并通过 wheel `RECORD` 的 SHA-256/大小核验。14 个 wheel 的配置字符串归并为 3 种平台构建变体（Windows 2 wheels、macOS 4 wheels、Linux 8 wheels）；均包含 `--enable-libx264` 和 `--enable-libx265`。可读字符串中未见 `--enable-gpl`，这只描述所观察字符串，不能据此推断组件或许可义务不存在。
- 这是锁定 wheel 内可观测字符串的技术证据，不证明字符串完整、来源可信或构建过程可复现；也不映射完整 native 组件、确认 notice/源码义务、判定许可证适用性或批准发行。所有者仍须确定分发范围，并取得与拟分发 artifact hash 绑定的上游构建清单、组件 BOM、license/notice 和对应源码供适格人员审阅；`licenseConcluded` 继续为 `NOASSERTION`，P6 **NOT READY**。

## 固定 CTranslate2、ONNX Runtime、Rust 与 NumPy wheel 复核（2026-10-10）

以下为只读发行物检查；wheel/sdist 以内存读取，未安装或保留。本节报告发行物身份和可观察内容，不把文件名、字符串或上游构建脚本单独当成完整许可结论。

### CTranslate2 4.8.2 原生依赖

10 个锁定 wheel 覆盖 CPython 3.11/3.12、Windows x86-64、macOS x86-64/arm64、manylinux x86-64/aarch64。实测文件大小和 SHA-256 全部匹配 `uv.lock`。SHA-256 如下：

| 目标平台 | CPython 3.11 | CPython 3.12 |
|---|---|---|
| macOS arm64 | `cb2a5b4c206b3bd1f7f4b44d07e86e42050af6753053cdc86444f8d0ead9d6d8` | `fedda669421a57f8164568ee86ea265727016988d310fcc2e24ca30e9ec457cd` |
| macOS x86-64 | `8221875b09ef982e3579a5165f8c9fcfb3d5de0f710af228eca2f73d69635ace` | `5385f15493e7b6f41377da83d0d5afeb8e0f36188260722f3800c3c7121455af` |
| manylinux aarch64 | `3823c9883c2c410a76b2f19feda9da628a3c112cedfd912db815e0055c8235e2` | `781f835da7fdc4adcc38f9d674dbe9b37eaf3c9aee3b2bc17d684342ff59d549` |
| manylinux x86-64 | `a24e0a95151b970941867fec94c983df978630f1996242a587c072d455607d28` | `554a0b2abf098a11c66ef7930c0a05b3de683a455e8ea3f2e6ab6966aaabc136` |
| Windows x86-64 | `995938fcd24a1174a7abf9765e7fa216b5b91a1d8e8c4c8f383c7a186e8bab2e` | `d94421d565d0de61c032998f737a18942b0f2bef40c0424b1846ec6f67300105` |

All 10 archives lack paths named LICENSE, NOTICE, COPYING, or equivalent third-party license files. Windows wheels include `_ext.pyd`, `ctranslate2.dll`, `cudnn64_9.dll`, and `libiomp5md.dll`; macOS x86-64 wheels include `libiomp5.dylib`; Linux wheels include `libgomp-*.so.1.0.0` and CTranslate2 native libraries. macOS arm64 wheels have no separate OpenMP runtime dylib.

The fixed [v4.8.2 Windows build script](https://github.com/OpenNMT/CTranslate2/blob/v4.8.2/python/tools/prepare_build_environment_windows.sh) downloads cuDNN 9.10.2 and copies an Intel oneAPI 2025.3 `libiomp5md.dll`; it also sets `WITH_CUDNN=OFF`, so the publisher must clarify why the cuDNN DLL is bundled and whether the backend can use it. NVIDIA's [9.10.2 redistribution manifest](https://developer.download.nvidia.com/compute/cudnn/redist/redistrib_9.10.2.json) identifies cuDNN 9.10.2.21 and `cudnn/LICENSE.txt`; the [cuDNN SLA](https://docs.nvidia.com/cudnn/latest/reference/eula/) sets conditions for distributing designated runtime DLLs. No matching DLL hash, bundled license text, or application-use confirmation ties those materials to the locked wheel. The Intel DLL likewise lacks a version-matched `redist.txt`/equivalent, applicable EULA and third-party notices, plus a hash comparison to Intel's distribution. Linux `libgomp` is consistent with the upstream Linux build setting `OPENMP_RUNTIME=COMP`; GCC's [license header](https://github.com/gcc-mirror/gcc/blob/master/libgomp/libgomp.h) states GPLv3 with GCC Runtime Library Exception 3.1, but the exact wheel binary, compiler version and notices are not bound by build provenance.

**Disposition:** the package-level MIT declaration does not close native component obligations. Keep `licenseConcluded=NOASSERTION`; do not approve binary redistribution until the publisher supplies artifact-bound build provenance, native dependency inventory, component notices and the relevant NVIDIA/Intel/GCC license materials.

### ONNX Runtime 1.30.0 wheel notice and binary map

The locked CPython 3.11/Windows x86-64 wheel SHA-256 is `0edd0145a6e3fce8a1276491dc784d615e3c58bcb952c9b4e5c876d5c6a12ad7`. Its `ThirdPartyNotices.txt` is 344,457 bytes with SHA-256 `c53a76501ef60db6f865f20599f220761201ac4057683acefdab37d861b86622`. Three installed native files were separately hashed: `onnxruntime.dll` `44741724166ad61c8c82885e394793807f2cf5707c83b9e33c2d78d75c6e7650`, `onnxruntime_providers_shared.dll` `fabb99add45aa1a0386c80bc63e92479c5f56e9e95ab98c85fb7ad21c4092ce0`, and `onnxruntime_pybind11_state.pyd` `06b712319c15145ac68f6e0f2796ba53defc2dbdfe667a76ec7f5383798421ec`.

Binary strings/symbols provide evidence consistent with pybind11, Protobuf, ONNX, FlatBuffers, RE2, Abseil, WIL and nlohmann JSON. The official [v1.30.0 build setup](https://github.com/microsoft/onnxruntime/blob/v1.30.0/setup.py) bundles the full notice file, so it is a broad inventory and does not prove every entry is linked into this wheel. oneDNN is reported disabled and no DNNL DLL was found. No separate MKL/OpenMP DLL or import was identified, but static inclusion is not excluded. Mbed TLS appears in notices without an identified binary marker. Exact CI build logs, CMake cache, linker map/inputs and dependency manifest/SBOM are still needed to map notices to this artifact. Retain the full notice when distributing the wheel and keep `licenseConcluded=NOASSERTION`.

### Tokenizers, Ruff and NumPy locked artifacts

- PyPI's fixed-version file indexes report filename, size and digest matching every locked file record for Tokenizers 0.23.2 (17 records), Ruff 0.14.14 (19), NumPy 2.4.6 (30) and NumPy 2.5.3 (12). Twelve selected Windows x86-64, Linux x86-64 and macOS arm64 wheels were also read and hashed directly against `uv.lock`; none were retained. PyPI returned `provenance: null` and `attestations: null` for these four releases.
- The 12 directly inspected wheel hashes are:

| Locked wheel filename | SHA-256 |
|---|---|
| `tokenizers-0.23.2-cp310-abi3-win_amd64.whl` | `2e96f5699d5249c9c64aa8412e044f727aae3a4098cf830f9901ec1afc361cde` |
| `tokenizers-0.23.2-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` | `41c2f84d172449b4dadb9cdc508e3e364076613c35b16e76ecfe47a60d1e3305` |
| `tokenizers-0.23.2-cp310-abi3-macosx_11_0_arm64.whl` | `986670e43691469dcee610ea0f846f91a8f84e91fc6f7a48d4c064414c0ec2bf` |
| `ruff-0.14.14-py3-none-win_amd64.whl` | `3dde1435e6b6fe5b66506c1dff67a421d0b7f6488d466f651c07f4cab3bf20fd` |
| `ruff-0.14.14-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` | `bb8481604b7a9e75eff53772496201690ce2687067e038b3cc31aaf16aa0b974` |
| `ruff-0.14.14-py3-none-macosx_11_0_arm64.whl` | `026c1d25996818f0bf498636686199d9bd0d9d6341c9c2c3b62e2a0198b758de` |
| `numpy-2.4.6-cp311-cp311-win_amd64.whl` | `1e254a00cdf42b1e4d5b3d68d33af63268d41340d8885df2ab6470f2e1500147` |
| `numpy-2.4.6-cp311-cp311-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl` | `89cd468399cfd2504718f0ba50e410dca55a170b61a02ad92bb18c8a65186e93` |
| `numpy-2.4.6-cp311-cp311-macosx_11_0_arm64.whl` | `110f8b71aacb688ec69062bb7f6938a0f8acb01b7c1c4beb453c65b6d234584d` |
| `numpy-2.5.3-cp312-cp312-win_amd64.whl` | `0a59a421a32580a009e8a1751345bf829631b990dc1794b80514ab722b435def` |
| `numpy-2.5.3-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl` | `b7e18c623bb5c95acb3b3328861272816ba199fb531921c5d6d0b675f1fde9e3` |
| `numpy-2.5.3-cp312-cp312-macosx_11_0_arm64.whl` | `f59a878c33d6b88122d80d239bb3b845d58708750b0cb06a09aebb9b18ec696c` |
- Tokenizers' exact locked sdist SHA-256 is `7f0f085686b9de0d0079e6f874ae053600db64c5d13049e0bbc0119926d25aac`; `bindings/python/Cargo.lock` SHA-256 is `b1d180c13b28254858aaf9778e62204ad6ae94531b26421227b0ed5be565d0bf` and has 153 package records (151 registry, 2 workspace). The sdist has an Apache-2.0 root LICENSE. The inspected wheels contain no license/notice paths. A source Cargo.lock does not attest which resolved dependency/features were compiled into a wheel or whether its notices were included.
- Ruff's exact locked sdist SHA-256 is `2d0f819c9a90205f3a867dbbd0be083bee9912e170fd7d9704cc8ae45824896b`; its `Cargo.lock` SHA-256 is `1988e8949c1387003cc31937fbfebc9e1a0a0d61f1dfe40c71576875026168d1` and has 528 records (478 crates.io, 4 git and 46 workspace/local). The sdist includes its MIT root LICENSE, MIT/Apache-2.0 materials for `ruff_annotate_snippets`, and a vendored typeshed LICENSE. The inspected wheels include the main MIT LICENSE but no third-party Rust license/notice bundle. Ruff is currently a dev dependency; the owner must decide whether it is part of any delivered product.
- Six sampled NumPy wheels (2.4.6 CPython 3.11 and 2.5.3 CPython 3.12 across Windows, Linux and macOS arm64) declare `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`. Each contains 20 license files (19 paths with `LICENSE` in the name and one `COPYING`: 17 under `.dist-info/licenses/` and 3 package-level copies); size and RECORD hash match for all 120 files. Except the top-level `.dist-info/licenses/LICENSE.txt`, the other 19 texts are identical across all six after CRLF/LF normalization. The top-level LICENSE is platform-specific (45,831 bytes for Windows, 46,794 for Linux, 46,826 for macOS arm64; the two package versions match within each platform).
- The license files identify libdivide as Zlib, pythoncapi-compat as 0BSD, Highway as Apache-2.0 OR BSD-3-Clause with a separate CC0-1.0 file-level grant, dragon4 as MIT, and PCG64/SFC64 as MIT. Other attached sources (x86-simd-sort, SVML, pocketfft, NumPy ma, random distributions, MT19937 and Philox) contain BSD three-clause text; the bundled top-level notice identifies OpenBLAS as BSD-3-Clause and LAPACK as `BSD-3-Clause-Open-MPI`. The latter is an SPDX-listed identifier ([SPDX License List](https://spdx.org/licenses/)); the NumPy random notice describes NCSA and BSD-3-Clause as alternative licenses (`NCSA OR BSD-3-Clause`). SplitMix64 makes a public-domain dedication without an unambiguous standard SPDX identifier. These observations support a file-level license map, not a legal conclusion or a package-wide expression for all wheel contents.
- Platform-specific bundled notice text says Windows statically links the GCC runtime into GCC-compiled files and does not list libquadmath; Linux/macOS notices describe dynamic libgfortran and libquadmath libraries, and identify libquadmath under LGPL-2.1-or-later. The wheel notice alone does not establish the exact native binary or linkage relationship. Keep separate platform BOM/notice records, map the cited runtimes to exact wheel files and build configuration, and preserve matching source/redistribution materials if required. The six-wheel license-text comparison is representative; §145 separately checks license-member byte coverage across all 40 locked NumPy wheels, and the 2026-10-11 native-member inventory below checks native-file presence without concluding linkage or license applicability.

**Disposition and actions:** keep current SPDX package `licenseDeclared` values; every `licenseConcluded` remains `NOASSERTION`. To close P6, first define whether optional ASR/browser dependencies and dev tools are included in the product. For every in-scope wheel, preserve the locked artifact hash and file-level license index; request artifact-bound Cargo build SBOM/active feature set and complete notices for Tokenizers/Ruff, and for NumPy map platform-specific GCC/libquadmath notices to exact binaries and build/link evidence across every intended platform. Resolve the NCSA alternative expression and SplitMix64 dedication with the project license reviewer. No binary redistribution approval follows from this review.

## 2026-10-10 锁定构建与校验工具增补

- `uv.lock` 现有 42 个包记录：项目 1 个、第三方 41 个。相较原锁，增加 `editables==0.5`、`hatchling==1.27.0`、`pathspec==1.1.1`、`python-dateutil==2.9.0.post0`、`six==1.17.0`、`skills-ref==0.1.1`、`strictyaml==1.7.3` 和 `trove-classifiers==2026.9.21.13`。其中 Hatchling/editables 用于默认构建组，skills-ref 及传递依赖属于 dev 工具链，不是项目运行依赖。
- 新增 8 行均选择 `uv.lock` 固定的 sdist，并核对下载 URL、大小和 SHA-256；从归档读取 PKG-INFO，逐一核对包名、版本、许可证字段和值的 SHA-256。作者元数据中有效 SPDX 表达式为 Hatchling `MIT`、Six `MIT`、skills-ref `Apache-2.0` 和 StrictYAML `MIT`。Editables、Pathspec、Trove Classifiers 的 sdist 未记录许可证字段；它们的锁定 wheel 许可证文件已在下方后续补查。python-dateutil 的 `License: Dual License` 不是有效 SPDX 表达式，未擅自映射。其余新增 artifact 的许可证文件、bundled components 和通知仍需按发行范围复核。
- §83 的 2026-10-10 wheel 许可证补充快照为 **41 packages, 46 artifacts, 41 metadata, 7 license, 1 notice members**；生成 SBOM 有 42 个 package records、58 个 relationships，其中 40 个第三方包有 `licenseDeclared`。`python-dateutil` 的 `Dual License` 当时仍保持 `NOASSERTION`；§86 后续已补证。此前 §64/§67 的测试数字是相应历史快照；该历史验证记录为 50 passed、3 skipped。构建/校验工具许可与交付范围仍需项目所有者在 P6 中决定。

## 2026-10-10 python-dateutil 锁定 sdist 许可证补充

- 对 `uv.lock` 中 `python-dateutil==2.9.0.post0` 的精确 sdist 做 SHA-256/大小核验，并读取归档内 `python-dateutil-2.9.0.post0/LICENSE`。锁定归档 SHA-256：`37dd54208da7e1cd875388217d5e00ebd4179249f90fb72437e91a35459a0ad3`；LICENSE 成员 SHA-256：`ba00f51a0d92823b5a1cde27d8b5b9d2321e67ed8da9bc163eff96d5e17e577e`。
- 上游精确版本 [LICENSE](https://github.com/dateutil/dateutil/blob/2.9.0.post0/LICENSE) 说明 BSD 条款适用于所有代码，包括同时受 Apache 2.0 覆盖的代码。SBOM 将该共同适用表达式记为 `BSD-3-Clause`，并保留精确 artifact/member 哈希、路径及 review note；`Dual License` 元数据仍原样留在证据记录中，不把它当作 SPDX 表达式。
- 该包级 `licenseDeclared` 解决了第三方包声明覆盖率，但不是法律意见，也不代表 bundled/native 文件或分发条件已审完；所有 `licenseConcluded` 仍是 `NOASSERTION`。§86 时点离线 verifier 计数为 **41 packages, 46 artifacts, 41 metadata, 8 license, 1 notice members**；审核报告 §89 曾记录 54 artifacts、41 metadata、9 license、2 notice、63 supplemental 的快照，NumPy 扩充后的当前计数见 §145。项目 LICENSE、分发范围、组件 notice/provenance 与远端 CI 仍是开放项。

## 2026-10-10 Playwright 1.63.0 跨平台 wheel 许可证文件索引

- 从 `uv.lock` 固定的 8 个 Playwright wheel 读取所有名称包含 LICENSE/NOTICE/COPYING 等标记的成员。8 个 wheel 合计 339,357,074 bytes；逐件确认 artifact SHA-256/大小与锁文件一致。每个 wheel 都有相同的 8 个候选路径，共 64 个成员；每个成员的 SHA-256/大小与所属 wheel 的 `RECORD` 一致。
- 候选包括 Python wheel 的 `.dist-info/licenses/LICENSE`、Playwright 包的 `LICENSE`/`NOTICE`/`ThirdPartyNotices.txt`、Node driver 级 `LICENSE`，以及 `serverRegistry.js.LICENSE`、`utilsBundle.js.LICENSE`、`webp_codec.LICENSE` 三个相邻 bundle sidecar。`ThirdPartyNotices.txt` 说明 sidecar 对应 `lib/` 下内联第三方 npm 包的完整许可文本。除了随平台变化的 driver LICENSE，其他 7 项内容在 8 个 wheels 中完全相同。此项检查核对文件存在和字节完整性，不替代逐个识别所有依赖，也不把归档内声明视为再分发批准。
- `docs/third-party-license-evidence.json` 将一个锁定 wheel LICENSE 绑定为 Playwright 包级 `Apache-2.0` 依据，并通过 `artifact_members` 记录其余 63 个 wheel 成员（主 LICENSE 另列）；验证器会复核所有归档身份、成员路径、摘要和大小。§87 时结果为 41 packages、53 artifacts、41 metadata、9 license、1 notice、63 supplemental members；41/41 个第三方包均有 evidence-backed `licenseDeclared`。定向 SPDX 回归 56 passed、3 skipped；之后补入的 ONNX Runtime CPython 3.12 wheel notice 见审核报告 §89，Playwright sidecar 组件见 §91，NumPy 扩充后的当前总计数见 §145。
- 此索引不覆盖 Playwright setup 另行下载的 Chromium 或 browser binary，也不映射 Node/Rust/native 组件的每项义务。项目许可证、分发范围、原生构建来源和远端矩阵 CI 仍未完成；所有 `licenseConcluded` 继续为 `NOASSERTION`。

### proxy-agent-negotiate@1.1.0 provenance and license text check

- The Playwright Windows x64 sidecar lists `proxy-agent-negotiate@1.1.0` as MIT, but the bundled sidecar does not include the license text. The exact npm registry tarball was downloaded and verified against its published SHA-512 integrity: 1,924 bytes, SHA-256 `6eec23d5d381a8b0ffafe91c19876d3a052e463618695981a7529f3a8bca1997`. It contains five files; `package/package.json` (972 bytes, SHA-256 `7b7c2579ea138d20d4f7699ca78ef16c526f35168dbf694f1d47cc861b0954d`) declares MIT, and the tarball contains no LICENSE file.
- The [npm provenance attestation](https://registry.npmjs.org/-/npm/v1/attestations/proxy-agent-negotiate%401.1.0) subject digest matches the exact tarball's published SHA-512 integrity, and its claimed repository/workflow/source commit match the [upstream release tag](https://github.com/TooTallNate/proxy-agents/releases/tag/proxy-agent-negotiate%401.1.0) and checked source tree at commit `b7e5f7ccce1a3ac5b339cc4c587974e8989cbc16`. This review did not independently verify the Sigstore signature or transparency-log inclusion; the npm `gitHead` field remains null.
- **Disposition:** keep `licenseDeclared=MIT` as the upstream package declaration and `licenseConcluded=NOASSERTION`. The checked tarball and source tree do not supply the license text. Provenance is supported by the registry's attestation claim, but its signature and transparency-log inclusion remain independently unverified; this is not a legal conclusion about the package's terms or redistribution obligations. The byte-level audit evidence is recorded in `PROJECT_AUDIT_REPORT.md` §92.

## 2026-10-11 NumPy native-file member cross-check

- The read-only `scripts/inventory_numpy_native_members.py` pass checked all 40 NumPy wheel sizes and SHA-256 values against `uv.lock`, hashed native-file candidates without installing wheels or extracting members to disk, and confirmed each member's size and SHA-256 against its wheel `RECORD` entry. It now copies and hashes each cache object through one identity-checked handle, then parses that same verified temporary snapshot, closing a cache-path replacement gap between verification and ZIP scanning. Candidate members are streamed/decompressed in memory for hashing. The resulting [`numpy-native-member-evidence.jsonl`](numpy-native-member-evidence.jsonl) has 1,130 rows totaling 1,209,167,565 uncompressed member bytes; its SHA-256 is `69b43a4fe83282af8a856890308f964308edecc636c520c84fc7dae514cd717e`.
- The archive contains `libgfortran`-named files in all 8 manylinux and 6 musllinux wheels plus 8 macOS wheels; `libquadmath`-named files in 4 manylinux x86-64, 3 musllinux x86-64, and 8 macOS wheels; and `libgcc_s`-named files in 6 musllinux and 8 macOS wheels. OpenBLAS-named files occur in 29 wheels across Windows x64/arm64, macOS, manylinux and musllinux. These names and hashes establish archive-member presence, not which files are imported, loaded, or linked into a given extension.
- **Disposition:** the exact native-member inventory narrows the file-to-artifact gap but does not supply an import table, linker map, active build configuration, or source/build provenance. Do not infer that a platform notice applies—or does not apply—to an observed member from its filename alone. Keep `licenseConcluded=NOASSERTION`; request artifact-bound build inputs/notices and retain the owner/reviewer decisions listed in the NumPy wheel review. P6 remains **NOT READY**.

## 2026-10-11 Windows capture-pipe source prototype dependency scope

- `native/windows/capture-pipe/CapturePipe.csproj` targets `net10.0-windows` / `win-x64` and declares no `PackageReference`; its local restore assets likewise resolve no NuGet package libraries. This source prototype adds no third-party NuGet package records to the current SBOM.
- The local Windows CI job uses the pinned .NET SDK 10.0.401 and runs build plus `--self-test`; no remote Actions run has been recorded. The project is not currently an installed service or bundled release artifact.
- Before distributing a self-contained service/runtime or native worker, review the exact .NET runtime/native component inventory, notices, build provenance, and applicable license obligations for the approved release scope. The prototype's empty NuGet dependency graph does not establish a complete service/runtime SBOM or distribution approval.

## 2026-10-11 NumPy all-wheel license-member follow-up

- Downloaded all 40 NumPy wheels listed in `uv.lock` (29 for 2.4.6, 11 for 2.5.3; 508,969,989 compressed bytes) from `files.pythonhosted.org` into a temporary cache. Every artifact's size and SHA-256 matched the lock. No wheel was installed or extracted.
- Indexed 43,630 archive members. All 40 wheel `METADATA` files declare `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`. Each wheel has 20 license/notice-name candidate files; all 800 candidate sizes and SHA-256 values match the wheel's `RECORD`. The separate [NumPy wheel review](NUMPY_WHEEL_LICENSE_REVIEW.md) describes the method; [the JSONL evidence](numpy-wheel-license-evidence.jsonl) binds each member to its locked wheel SHA-256 and records the normalized text hash. Its SHA-256 is `0bf010302e664ffec7a1eb15feea2629b46c1b30f5365d879cd7efd94cef96f9`.
- After CRLF/LF normalization, 17 of 18 canonical candidate paths have the same text hash across all versions, OS, architectures and CPython/PyPy tags. The top-level `.dist-info/licenses/LICENSE.txt` is platform-specific: macOS 46,826 bytes (`649a589ab31076e79e9ce62ba24eae9959598124176640dbc95f87bd10f34fcf`), Linux 46,794 bytes (`4860083caa0de2ac3292ca98bd074bd8f45d8b32624e37b1e70a240bff61e488`), and Windows 45,831 bytes (`dc97d59562c75c04557f1e9a68f3eae326699eb119d569cd4ed6a4eafe5f9abb`). The same platform hash repeats across both NumPy versions and all locked architecture/runtime variants.
- At the §145 historical checkpoint, all 40 wheel artifact identities and 800 candidate members had been added to `third-party-license-evidence.json`; the verifier then covered **41 packages, 94 artifacts, 41 metadata, 9 license, 2 notice and 863 supplemental members**. §161 later expanded exact member evidence to 210 artifacts and 1,149 supplemental members. The regenerated SBOM contains 121 package records and 137 relationships; the pinned SPDX 2.3 schema passes, and every `licenseConcluded` remains `NOASSERTION`.
- This closes NumPy wheel identity and license-file byte coverage for the locked set. It does not map GCC/libquadmath notices to exact compiled binaries, establish native build provenance or linker inputs, resolve NCSA's alternative expression or SplitMix64's dedication, or approve redistribution. The project release scope and license-owner decisions remain open.

## 2026-10-11 Locked Windows PE import map for CTranslate2 and ONNX Runtime

- Added [`inventory_locked_pe_imports.py`](../scripts/inventory_locked_pe_imports.py), a standard-library PE32/PE32+ reader for direct normal and delay-load DLL imports. It runs offline, copies each selected cache object through one identity-checked file handle into a temporary snapshot, verifies its locked size/SHA-256 before ZIP parsing, bounds archive/member/header/import reads, does not extract members, and verifies each parsed `.dll`/`.pyd` member against its wheel `RECORD`. [`windows-pe-import-evidence.jsonl`](windows-pe-import-evidence.jsonl) records the lock SHA-256, wheel URL/hash/size, member path/hash/size, RECORD digest/status, machine/PE format and parsed imports.
- The first pass used the then-existing cache (3 of 6 wheels). To complete this bounded map, the other three exact lockfile wheels were downloaded from `files.pythonhosted.org` into a separate private PE-audit cache. All **6/6** wheel files now match their locked sizes and SHA-256 values; the dedicated cache contains **95,405,677 bytes**. At this earlier checkpoint, the SPDX member-evidence cache covered 94 of 235 unique locked artifacts; §161 later expanded it to 210. The separate complete lock-byte cache and verifier are recorded in §159 of PROJECT_AUDIT_REPORT.md. The JSONL now has **20 PE-member rows** (8 CTranslate2, 12 ONNX Runtime) and **250 import entries** (242 normal and 8 delay-load). All member sizes/digests match their wheel `RECORD`; AMD64 wheels parse as PE32+ `0x8664` and ARM64 wheels as PE32+ `0xaa64`. JSONL SHA-256: `f7eae8f513d60e18b33413c1377441758ab2a379e88d743e404c717d21339d91`.
- Both CTranslate2 x64 Python wheels have the same observed import shape: `_ext.pyd` imports `ctranslate2.dll` and the matching Python DLL; `ctranslate2.dll` imports `libiomp5md.dll` plus Windows/MSVC runtime DLLs. The included `cudnn64_9.dll` has only a parsed normal `KERNEL32.dll` import. `libiomp5md.dll` imports `WINTRUST.dll`, `imagehlp.dll` and runtime DLLs.
- All four ONNX Runtime wheels (CPython 3.11/3.12, x64/ARM64) contain `onnxruntime.dll`, `onnxruntime_providers_shared.dll`, and `onnxruntime_pybind11_state.pyd`. The primary DLL and extension import Windows/MSVC runtime DLLs and delay-load `SHELL32.dll`; the providers DLL imports runtime DLLs and `KERNEL32.dll`. No separate MKL DLL appears in these direct import tables. That observation does not exclude static inclusion or runtime `LoadLibrary`/`GetProcAddress` behavior.
- The host has no detected `dumpbin`, LLVM PE inspection command, or `objdump`; the active Python 3.11 audit environment has neither `pefile` nor `lief`. The parser was instead tested against synthetic PE32 and PE32+ fixtures, including normal and VA/RVA delay imports, malformed headers, unbounded descriptors and ambiguous sections. This provides one parser's bounded structural reading, without an independent tool cross-check.
- This is a direct import-table map, not a complete transitive native BOM, symbol/linker map, loaded-module trace, source/build provenance record, or license analysis. Direct imports do not identify static libraries, dependencies requested through runtime APIs, or which code paths execute. Do not infer static linkage, component absence, license applicability, or redistribution permission from this map; keep SPDX `licenseConcluded=NOASSERTION`.
- **Validation:** `python scripts/inventory_locked_pe_imports.py --lock skills/douyin-transcript/uv.lock --cache-dir <private-PE-SHA-keyed-cache> --output docs/windows-pe-import-evidence.jsonl` returned **0**, reporting 6/6 wheels and 20 members; JSONL SHA-256 is recorded above. `python -m pytest -q --tb=short tests/unit/test_locked_pe_imports.py` returned **6 passed**; Ruff check/format and `py_compile` passed for the script and test. The six exact locked wheels were downloaded only for offline inspection; none was installed and no model was downloaded. P6 still requires artifact-bound publisher build inputs/notices and a reviewer to assess license obligations for the owner-approved release scope.


## 2026-10-11 Complete locked-artifact byte cache

- A separate private SHA-256-keyed cache now contains all 235 artifact identities referenced by the current uv.lock: 42 package records and 2,097,567,472 compressed bytes. Every cached file was checked against the lock entry size and SHA-256. The cache contains no additional files after cleanup.
- The retained [lock-artifact evidence manifest](locked-artifact-cache-evidence.jsonl) records each package/version, artifact URL, digest, size, lock digest and local verification status. Its SHA-256 is 5c2f50c8a87d2117aeae60ab3b90ae61b084b90e8e11d15d5584be046a44afa0.
- Run the offline checker with the repository lock and private cache: python scripts/verify_locked_artifact_cache.py --lockfile skills/douyin-transcript/uv.lock --cache-dir <private-sha256-cache>. This proves only that local bytes match the lockfile. It does not validate archive members, publisher provenance, build inputs, linkage, license applicability or redistribution permissions.
- SPDX member-level evidence currently covers 210 artifacts, 41 metadata members, 9 license members, 2 notice members and 1,149 supplemental members (§161). The §159 complete raw-byte cache alone did not expand member evidence; the subsequent §161 reconciliation added exact hashes for 286 previously unbound regular files. Neither byte identity nor filename candidates establish license applicability or approval.

## Locked Windows PE import inventory and corrected evidence (§166/§172)

- The earlier CTranslate2/ONNX-only table above is a historical subset. The same offline reader now scans every Windows wheel referenced by the current `uv.lock` and considers `.exe`, `.dll` and `.pyd` members. It verifies each complete wheel snapshot against the lock size/SHA-256, checks PE32/PE32+ bounds and records whether each PE machine matches its wheel platform, reads imports without extracting members, and records wheel `RECORD` status separately. A missing wheel fails the run instead of producing a partial success.
- The current private SHA-256 cache supplied **40/40** locked Windows wheels covering 11 packages. It produced **419 PE members** (97 DLL, 6 EXE, 316 PYD), including 62 PE32 and 357 PE32+ images (62 x86, 277 AMD64, 80 ARM64), and **2,654** direct normal/delay import entries. Exact comparison with the complete locked archive member index found the same 419 `(artifact SHA-256, path)` keys and member sizes, with no missing/extra candidate.
- §172 corrected the initial RECORD path comparison: archive paths use `/`, while three Ruff Windows RECORD paths use `\`. After normalizing separators and preserving the original RECORD path, all 419 PE members have matching RECORD hashes and sizes, including the three `ruff.exe` members. The Playwright win32 wheel still contains an AMD64 `node.exe`; this platform mismatch remains. V1 URL capture targets Windows 11 x64; do not imply 32-bit Windows support unless this is resolved.
- [`windows-pe-import-evidence-complete.jsonl`](windows-pe-import-evidence-complete.jsonl) is the preserved §166 historical snapshot (419 rows; 420,779 bytes; SHA-256 `1e620e1ee71ada28f2e958d43017eb15ce311061507e168673611a8104780ca0`). It still records 416 verified rows and three Ruff `missing_from_record` rows from the original separator-comparison bug; do not cite it as current corrected RECORD evidence. The current corrected file is [`windows-pe-import-evidence.jsonl`](windows-pe-import-evidence.jsonl) (419 rows; 446,135 bytes; SHA-256 `18236b199a2cd5e8d6db98beec04447546e799c9153a46085274c14c2ff570ae`), with all 419 rows verified. [`windows-pe-import-edges.jsonl`](windows-pe-import-edges.jsonl) binds to this corrected inventory hash. The §172 focused PE group passed 22 tests; no wheel was downloaded or installed for that run.
- The broader map remains a static archive import-table snapshot. It cannot identify static linking, runtime `LoadLibrary`/`GetProcAddress` modules, transitive symbol usage, build inputs/provenance, or license applicability. No SPDX license field or project release decision changed; `licenseConcluded` remains `NOASSERTION`. Owner-approved distribution scope, project LICENSE, native notice/linkage review, remote CI and clean remote install remain open.
