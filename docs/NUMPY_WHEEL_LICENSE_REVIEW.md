# Locked NumPy wheel license-file review

Date: 2026-10-11

## Scope and method

- Reviewed every NumPy wheel recorded in `skills/douyin-transcript/uv.lock`: 29 wheels for NumPy 2.4.6 and 11 for NumPy 2.5.3, 40 artifacts total (508,969,989 bytes). The wheel bytes were downloaded from `files.pythonhosted.org` into a temporary cache, then each file's size and SHA-256 were checked against the lock. No wheel was installed or extracted.
- The locked-artifact inventory scanner read 43,630 archive members. Each wheel's `METADATA` reports the same `License-Expression`: `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`.
- Every wheel contains 20 license/notice-name candidate files. For all 800 files, the archived size and SHA-256 match that wheel's `RECORD`. The evidence rows are in [`numpy-wheel-license-evidence.jsonl`](numpy-wheel-license-evidence.jsonl); SHA-256: `0bf010302e664ffec7a1eb15feea2629b46c1b30f5365d879cd7efd94cef96f9`.
- After normalizing line endings and removing the version-specific `.dist-info/licenses/` prefix, the 800 files map to 18 candidate paths. Seventeen paths have one normalized content hash across all versions, operating systems, architectures and CPython/PyPy tags. The top-level `LICENSE.txt` has three hashes, matching the Windows, macOS and Linux groups; the same platform-specific text hash repeats across versions and architectures.
- At the §145 snapshot, `docs/third-party-license-evidence.json` bound these 40 wheel identities and 800 candidate members; the offline verifier then covered **41 packages, 94 artifacts, 41 metadata members, 9 license members, 2 notice members and 863 supplemental members**. §161 later expanded member-level coverage to 210 artifacts and 1,149 supplemental members. The generated SPDX document contains 121 package records and 137 relationships and passes the pinned SPDX 2.3 schema.

## Native-file member inventory

- `scripts/inventory_numpy_native_members.py` reads the cached wheel bytes without installing them or extracting members to disk. It copies each wheel through one identity-checked file handle into a temporary snapshot while computing SHA-256, then parses that same verified snapshot; candidate members are streamed/decompressed for hashing. It checks each of the 40 wheel sizes and SHA-256 values against `uv.lock`, hashes every native-file candidate, and checks the member size and SHA-256 against that wheel's `RECORD` row.
- The inventory contains **1,130 members** totaling **1,209,167,565 uncompressed bytes**. It covers 10 Windows wheels (`win32`, `win_amd64`, and `win_arm64`), 16 macOS wheels, 8 manylinux wheels (x86-64 and aarch64), and 6 musllinux wheels (x86-64 and aarch64). The JSONL is [`numpy-native-member-evidence.jsonl`](numpy-native-member-evidence.jsonl), SHA-256 `69b43a4fe83282af8a856890308f964308edecc636c520c84fc7dae514cd717e`.
- The records show `libgfortran` members in all 8 manylinux and 6 musllinux wheels; `libquadmath` members in 4 manylinux and 3 musllinux wheels; and `libgcc_s` members in all 6 musllinux wheels. Eight macOS wheels contain `libgfortran.5.dylib`, `libquadmath.0.dylib`, and `libgcc_s.1.1.dylib`. OpenBLAS-named members occur across the platform families. These are archive-presence observations, not proof that every file is loaded or linked into a particular extension.
- Reproduce from an already populated SHA-256-keyed wheel cache with `python scripts/inventory_numpy_native_members.py --lock skills/douyin-transcript/uv.lock --cache-dir <sha256-keyed-wheel-cache> --output docs/numpy-native-member-evidence.jsonl`. The script does not download artifacts.

## Remaining obligations

This review establishes wheel identity, package metadata, license-member coverage, native-file member presence and member byte integrity. It does not map each license to compiled native code or establish build provenance, import/link tables, or linker inputs. In particular, the platform notices' GCC/libquadmath references still need artifact-bound build evidence and an applicable-license disposition. NCSA's alternative expression and the SplitMix64 public-domain dedication also need an owner or license-reviewer disposition. Keep every `licenseConcluded` as `NOASSERTION`; do not treat this audit as permission to redistribute NumPy wheels or a product containing them.

See [`THIRD_PARTY_LICENSE_REVIEW.md`](THIRD_PARTY_LICENSE_REVIEW.md) for the broader third-party review and [`PROJECT_AUDIT_REPORT.md`](PROJECT_AUDIT_REPORT.md) §§145/147 for commands, evidence and project status.
