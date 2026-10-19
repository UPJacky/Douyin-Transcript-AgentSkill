# Third-party notices

## SPDX 2.3.1 JSON Schema

- File: `scripts/schemas/spdx-2.3.schema.json`
- Attribution: SPDX Project, *SPDX 2.3.1 JSON Schema*.
- Upstream source: [SPDX `support/2.3` schema](https://raw.githubusercontent.com/spdx/spdx-spec/support/2.3/schemas/spdx-schema.json).
- Upstream SHA-256: `4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212`; the vendored file is byte-identical.
- Upstream license: Creative Commons Attribution 3.0 Unported (CC BY 3.0); the official [legal code](https://creativecommons.org/licenses/by/3.0/legalcode.txt) is included at [THIRD_PARTY_LICENSES/CC-BY-3.0.txt](THIRD_PARTY_LICENSES/CC-BY-3.0.txt), SHA-256 `e6bc9e9c474700b708f568bac9e5a8a9bcb2b1dad53442f5ba449fcb848b8e76`. The license URI is <https://creativecommons.org/licenses/by/3.0/>.
- Changes to the schema: none. It is used by the repository's schema-checking tool, not as an application runtime dependency.

## `proxy-agent-negotiate` 1.1.0 upstream declaration record

- Upstream attribution: Nathan Rajlich; the pinned [package manifest](https://github.com/TooTallNate/proxy-agents/blob/b7e5f7ccce1a3ac5b339cc4c587974e8989cbc16/packages/negotiate/package.json) (SHA-256 `b5ea26c6def2543cf09d0e3011cd9bf6271c8212afe51306bc9c8337a1ec32aa`) declares `proxy-agent-negotiate@1.1.0` and MIT. The [source tree at commit `b7e5f7ccce1a3ac5b339cc4c587974e8989cbc16`](https://github.com/TooTallNate/proxy-agents/tree/b7e5f7ccce1a3ac5b339cc4c587974e8989cbc16/packages/negotiate) and the [release tag](https://github.com/TooTallNate/proxy-agents/releases/tag/proxy-agent-negotiate%401.1.0) were checked. The npm registry metadata reports `gitHead: null`; its [published provenance attestation](https://registry.npmjs.org/-/npm/v1/attestations/proxy-agent-negotiate%401.1.0) binds the release to this commit.
- The [npm 1.1.0 metadata](https://registry.npmjs.org/proxy-agent-negotiate/1.1.0) declares MIT. The exact [npm tarball](https://registry.npmjs.org/proxy-agent-negotiate/-/proxy-agent-negotiate-1.1.0.tgz) has SHA-512 integrity `N8IBcM3UgCVzz2L2Lqv8DVntDnnC8/hiV4nEDUPkqq72TPUgYWjQc+bdZlBPZK9LzPAvOY//gAt0S0DApoOXWQ==` and SHA-256 `6eec23d5d381a8b0ffafe91c19876d3a052e463618695981a7529f3a8bca1997`.
- On 2026-10-15, `npm audit signatures --json --include-attestations` returned no invalid or missing signatures/attestations. npm's Sigstore verifier accepted the GitHub Actions workflow identity, OIDC issuer, and transparency-log inclusion proof; the attestation subject digest matched the registry tarball integrity. The attested repository, workflow, and source commit match the checked upstream release. This verifies release provenance, not license applicability.
- The locked Playwright 1.63.0 Windows x64 wheel SHA-256 is `2f9a707a6c6c91157ed77bff2b8caeb04b3c8d46e70d585fc134298cbe4b5cc6`. Its `playwright/driver/package/lib/utilsBundle.js.LICENSE` member (SHA-256 `2495f30be29620d54b58339821eda0ebabdfb6ee9b09455f7285a06fd46fb9f3`) names this package/version and declaration.
- The sidecar member, exact npm tarball, and examined upstream release source tree contain no license text for this package. The project's first release is source-only and does not separately distribute this npm package. This entry records upstream metadata and the evidence gap only; it does not provide license text or determine license applicability. The SBOM `licenseConcluded` remains `NOASSERTION`.
