# WFP .NET 构建期依赖审查

- 审查日期：2026-10-12
- 范围：native/windows/wfp-policy-plan/packages.lock.json 与 native/windows/capture-pipe/ 的 NuGet 依赖。
- 结论：WFP policy-plan 当前锁定 4 个用于构建/源生成的 NuGet 包；它们不属于 Python 应用 SBOM，也不是当前 capture-pipe 的运行时依赖。该工具项目声明为不可部署的检查原型。若将来把服务、原生可执行文件或生成代码纳入发行物，须重新审阅包许可、notice 和生成输出的再分发边界。此表是技术证据，不构成法律结论或所有者发行批准。

## 项目边界

wfp-policy-plan 仅有 Microsoft.Windows.CsWin32 0.3.360 一个直接 PackageReference，且设置 PrivateAssets="all"；lockfile 解析出 3 个传递依赖。capture-pipe/CapturePipe.csproj 没有 PackageReference，该目录也没有 NuGet lockfile。CsWin32 是 source generator；其 README 说明生成 API 源码写入消费项目编译，不增加运行时依赖。微软 SDK/WDK metadata 包说明其 .winmd 数据用于生成语言投影，不能作为 CLR assembly 加载。参见 [CsWin32 NuGet 包](https://www.nuget.org/packages/Microsoft.Windows.CsWin32/0.3.360)、[Win32Docs 包](https://www.nuget.org/packages/Microsoft.Windows.SDK.Win32Docs/0.1.42-alpha)、[SDK metadata 包](https://www.nuget.org/packages/Microsoft.Windows.SDK.Win32Metadata/71.0.30-preview)、[WDK metadata 包](https://www.nuget.org/packages/Microsoft.Windows.WDK.Win32Metadata/0.13.25-experimental)。

## 锁定包与本地证据

全部包均从 lockfile 对应的 NuGet.org cache 找到 nupkg、nuspec、`.nupkg.metadata` 与 `.signature.p7s`；lockfile `contentHash` 与 `.nupkg.metadata` 相同，对 nupkg 原始字节计算的 SHA-512 与 `.nupkg.sha512` sidecar 相同。二者不是可直接比较的同一摘要：lock `contentHash` 是排除签名元数据的包内容 SHA-512，sidecar 是完整 `.nupkg` 归档 SHA-512。对签名包，两者预期不同；参见 [NuGet nupkg metadata 设计说明](https://github.com/NuGet/Home/wiki/Nupkg-Metadata-File)。下表 SHA-256 是本机对 nupkg 原始字节计算所得。

2026-10-12 用本机锁定 SDK 执行 `dotnet nuget verify --all`，对四个 lockfile 精确版本的缓存 `.nupkg` 全部返回退出码 0；验证器输出的四个 Content hash 分别与 lockfile 完全一致，并识别到每包的 Microsoft author signature 与 NuGet.org repository signature。Win32Docs 的 author/repository 证书有效期止于 2023/2024，但验证仍返回成功。命令未单独展开时间戳链细节，因此不据此断言具体信任路径；这也不是许可证适用性结论。当前发行范围、生成输出的许可适用性和 owner approval 仍未确认。

**§231 fresh-source reconciliation：** 使用仓库固定 .NET SDK 10.0.401，为 NuGet packages、HTTP cache 及 plan/Core MSBuild `obj` 配置新的临时隔离目录；仅指定 `https://api.nuget.org/v3/index.json` 并运行 `dotnet restore WfpPolicyPlan.csproj --locked-mode --force --source ... --packages <temporary-packages> -p:NuGetAudit=false`。restore 成功取得四个精确包，四个新缓存 `.nupkg.metadata` `contentHash` 均与 lockfile 一致；四个完整 `.nupkg` raw SHA-512 均与 sidecar 一致，且各自与 lock `contentHash` 不同，符合签名摘要定义。针对隔离 cache 的四个归档分别运行 `dotnet nuget verify --all` 均退出码 0，并识别 author/repository signature。详见 [PROJECT_AUDIT_REPORT.md §231](PROJECT_AUDIT_REPORT.md)。

| 包（精确版本） | 角色 | NuGet 许可元数据与随包文件 | 本机 nupkg SHA-256 | 来源与未闭合事项 |
|---|---|---|---|---|
| Microsoft.Windows.CsWin32 0.3.360 | Direct；编译期 source generator | nuspec 为 SPDX MIT；developmentDependency=true，不要求接受许可。包内含 51,294-byte NOTICE.txt（列 17 个第三方组件：2 个 Apache-2.0、15 个 MIT）与 SPDX 2.2 manifest。 | 3892e02f320ec5ae0cedd0c3879073e3492202a2ae03787d3778df6596cd0699 | NuGet 来源为 nuget.org；nuspec repository 指向 microsoft/CsWin32 commit 505d80fc4e8f5705add39d3cc5fbd594ced5491f。若未来分发该工具或包内文件，应保留并审阅 NOTICE。 |
| Microsoft.Windows.SDK.Win32Docs 0.1.42-alpha | Transitive；编译期 Win32 API 文档输入 | nuspec 未提供 <license>，仅有 licenseUrl=https://aka.ms/WinSDKLicenseURL 且 requireLicenseAcceptance=true；nupkg 无许可证文本、README 或 NOTICE。 | e83bf398dceb1957d698d24daa8a23f986beedb0109727a0ee99b229a525230b | 项目 URL 指向 microsoft/win32metadata，nuspec repository commit 为 35b4ae8bdb4362a8d19daa0397a0b5f07cd2794d。审查时官方 aka.ms 许可链接不可读取；包级适用条款仍未确认。不得从同组其他包推定。 |
| Microsoft.Windows.SDK.Win32Metadata 71.0.30-preview | Transitive；SDK Win32 .winmd 生成输入 | nuspec license type=file，包内 sdk_license.txt 为 Microsoft Windows SDK Software License Terms，大小 28,670 bytes，SHA-256 0e97876eaa1fc79558e0d51dc0bee286d36dca8e95f7876259ffdf947396bca1；requireLicenseAcceptance=true。 | b1f4ae72797e76c7512f08ba24ee3fd2deff01c26a7d812083d56229f7d62a3b | 来源仓库为 microsoft/win32metadata，nuspec 未固定 source commit。应在决定发行生成代码或原生服务前确定该文件对生成输出的适用范围。 |
| Microsoft.Windows.WDK.Win32Metadata 0.13.25-experimental | Transitive；WDK .winmd 生成输入 | nuspec 同样以包内 sdk_license.txt 声明 Windows SDK Software License Terms；文件 SHA-256 与上一包相同，requireLicenseAcceptance=true。 | 79079a449d8f621052bcaf13039e411d1c1b77aec4a89cf04d96518d0a619617 | 来源仓库为 microsoft/wdkmetadata，nuspec 未固定 source commit。其最小依赖版本是 SDK metadata 63.0.31-preview，而当前 lock 解析到 71.0.30-preview；该版本范围不是第五个已锁定包。 |

NuGet Gallery 可查看 [CsWin32](https://www.nuget.org/packages/Microsoft.Windows.CsWin32/0.3.360)、[Win32Docs](https://www.nuget.org/packages/Microsoft.Windows.SDK.Win32Docs/0.1.42-alpha)、[SDK Win32Metadata](https://www.nuget.org/packages/Microsoft.Windows.SDK.Win32Metadata/71.0.30-preview) 和 [WDK Win32Metadata](https://www.nuget.org/packages/Microsoft.Windows.WDK.Win32Metadata/0.13.25-experimental) 的版本/项目元数据。NuGet 官方文档解释了锁定依赖版本范围语义：[Package versioning](https://learn.microsoft.com/en-us/nuget/concepts/package-versioning)。Win32Docs 指向的 [Windows SDK license URL](https://aka.ms/WinSDKLicenseURL) 在本次审查环境无法读取；这不证明链接不可用，也不解决该包的适用条款。

## 独立 Windows 构建 BOM（2026-10-12，§217）

本机已用仓库钉住的 .NET SDK 10.0.401，对 `Release/win-x64` 执行 no-restore 构建，并生成 [dotnet-windows-build-bom.json](dotnet-windows-build-bom.json)。该 BOM 记录 11 项仓库相对源输入、4 个锁定 NuGet 包、38 个该目标配置下的 CsWin32 生成源码及 5 个构建输出的大小/SHA-256；每个精确缓存包也重新运行 `dotnet nuget verify --all`，均成功。清单不含本机绝对路径、时间戳或账户信息。

**§220 更新：** 纯托管 `WfpPolicy.Core` 已作为 WFP plan 的项目引用；源输入闭包和 BOM generator 已扩展到该项目。当前清单记录 14 项源输入、相同的 4 个 NuGet 包、38 个 CsWin32 生成源码和 7 个构建输出。定向 BOM 回归为 7/7。§217 上述 11/5 计数是历史快照。该 BOM 仍仅是本地 build identity 证据，不是运行时 SBOM、清洁环境重现或许可结论。

在具有匹配 SDK、lockfile 依赖已缓存的 Windows checkout 中，可重建并更新清单：

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync python .\scripts\generate_dotnet_build_bom.py --dotnet "$env:TEMP\douyin-wfp-dotnet-sdk\dotnet.exe"
```

此记录绑定本机构建输入与输出身份，但没有固定 SDK 安装包本身的 SHA-256、没有在干净远端环境独立重现，也没有覆盖未来服务/安装器或运行时 SBOM。它不证明许可证适用性、代码签名、部署行为或发行批准；Win32Docs 条款及 SDK/WDK 许可对生成输出的适用范围仍待所有者/法律审阅。

## 后续处置

1. 保持 WFP 原型包与应用运行 SBOM 分开，不把 build-only 包误报成运行时依赖。
2. 在 Win32Docs 的许可条款获得可核查副本前，不把 WFP policy-plan 工具或其包作为发行物；不要将相邻 SDK metadata 包许可外推到 Win32Docs。
3. 若未来交付服务/生成源码，固定并记录所用包摘要与源提交，审查 CsWin32 NOTICE、SDK/WDK license 对生成输出的适用性，并生成独立的原生构建依赖清单。
4. NuGet lock-contentHash/raw-archive hash 关系已在 fresh locked restore 中独立复现并按签名语义核对。远端 CI、clean remote install、生成输出许可分析与法律适用性仍未完成。

## §255 BOM 刷新核验（2026-10-12）

使用 pinned .NET SDK 10.0.401 运行生成器的常规 build 路径后，BOM 按项目根目录计算的清单为：wfp-policy-plan 15 项源输入、38 项生成源、7 项构建输出；WfpPolicy.Core 24 项源输入、0 项生成源、24 项构建输出；native reader 12 项源输入、103 项生成源、10 项构建输出。合计 **51 项源输入、141 项生成源、41 项构建输出，共 233 项文件身份记录**，均包含大小和 SHA-256。四条锁定 NuGet 包记录另列，不计入 233 项。仓库内、生成和输出文件根路径解析后的核验结果为 **0 missing / 0 size-or-hash mismatch**；`--skip-build` 再生成的 BOM SHA-256 与当前文件一致：`D18946CD54E144A0E45D80FD782A32D4E1C331D25B5B9D2D6D286483437C5223`。定向回归 `tests/unit/test_dotnet_build_bom.py` 为 **10 passed、1 skipped**（当前 Windows 账户缺少 symlink privilege）。

这刷新的是本机构建输入/输出身份快照，不固定 SDK 安装包摘要、不证明远端 clean build、运行时依赖完整性、生成代码的许可适用性，也不替代 owner 发布批准。NuGet 包许可与生成输出范围仍按上文保持开放。
