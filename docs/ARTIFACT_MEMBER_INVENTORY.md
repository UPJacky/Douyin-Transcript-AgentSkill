# Locked artifact member inventory

Generated from the local SHA-256-keyed cache using `scripts/inventory_locked_artifact_members.py`.

> This file retains the earlier 54-artifact member-table snapshot. The complete §160 scan now covers all 235 lockfile artifacts; see [`artifact-member-inventory-complete.md`](artifact-member-inventory-complete.md), its [manifest](artifact-member-inventory-complete-manifest.json), and the three hash-pinned JSONL parts linked from the report. The complete scan adds name/path visibility only and does not expand the SPDX license evidence.

## Scope and method

- `uv.lock` SHA-256: `f4fc838d6f52555ca03ccf378c67e2a988666928904ff14bfab6d4af7c88f31b`.
- Lock coverage: 54 cached artifacts with exact lock identities out of 235 unique artifact identities in the lock; this is a cached evidence subset, not a complete inventory of all lock artifacts.
- A separate NumPy review now covers all 40 locked NumPy wheels and 800 RECORD-verified license/notice members; those wheel members are recorded in [`NUMPY_WHEEL_LICENSE_REVIEW.md`](NUMPY_WHEEL_LICENSE_REVIEW.md) and are not part of this 54-artifact member table.
- Cached artifact bytes whose SHA-256 values were checked: 463,169,799; expanded archive bytes traversed for tar indexing: 1,517,135,349.
- Archive member rows: 31,403; one JSONL row per member is in [`artifact-member-inventory.jsonl`](artifact-member-inventory.jsonl). Each row carries the artifact SHA-256, member path, declared uncompressed size, archive-entry type, and heuristic candidate labels; the table below maps each artifact SHA-256 to its lock URL, package, version, type, and filename.
- Every cached object matched a SHA-256, size, URL, package/version and artifact type recorded in `uv.lock`. ZIP/tar headers were read in place; no member was extracted to disk. The script did not download or install anything.
- Candidate labels are filename/path/extension signals only. They do not establish licensing, applicability, provenance, linkage or publication permission.

## Cached artifacts

| Package/version | Type | Filename | Lock URL | SHA-256 | Bytes | Members | Candidate members |
|---|---|---|---|---|---:|---:|---:|
| colorama 0.4.6 | sdist | colorama-0.4.6.tar.gz | https://files.pythonhosted.org/packages/d8/53/6f443c9a4a8358a93a6792e2acffb9d9d5cb0a5cfd8802644b7b1c9a02e4/colorama-0.4.6.tar.gz | `08695f5cb7ed6e0531a20572697297273c47b8cae5a63ffc6d6ed5c201be6e44` | 27,697 | 31 | 3 |
| trove-classifiers 2026.9.21.13 | sdist | trove_classifiers-2026.9.21.13.tar.gz | https://files.pythonhosted.org/packages/bf/93/af436dfaa845cab5d96f0adbc1e4f3730532d37fa249e4eb796fb1d7fc82/trove_classifiers-2026.9.21.13.tar.gz | `0a9ebc8d4e2f3e8a22848c5258033035bec17a3012ac3fea16dbaa764489eb71` | 17,085 | 32 | 9 |
| pyee 13.0.1 | sdist | pyee-13.0.1.tar.gz | https://files.pythonhosted.org/packages/8b/04/e7c1fe4dc78a6fdbfd6c337b1c3732ff543b8a397683ab38378447baa331/pyee-13.0.1.tar.gz | `0b931f7c14535667ed4c7e0d531716368715e860b988770fc7eb8578d1f67fc8` | 31,655 | 54 | 7 |
| onnxruntime 1.30.0 | wheel | onnxruntime-1.30.0-cp311-cp311-win_amd64.whl | https://files.pythonhosted.org/packages/66/68/b8aaade8c1883f569228f4b57201cce922bb7d4af6f977d619520a733430/onnxruntime-1.30.0-cp311-cp311-win_amd64.whl | `0edd0145a6e3fce8a1276491dc784d615e3c58bcb952c9b4e5c876d5c6a12ad7` | 14,309,136 | 323 | 13 |
| fsspec 2026.9.0 | sdist | fsspec-2026.9.0.tar.gz | https://files.pythonhosted.org/packages/77/cd/9be253869fc42e764de7f3dedd6969af7d44ff9c3375214a3442a6f3fc08/fsspec-2026.9.0.tar.gz | `0f08147951c8cb31d844c3547d631053b127863b60be04cf06e121333ee0e2fe` | 333,545 | 93 | 5 |
| pathspec 1.1.1 | sdist | pathspec-1.1.1.tar.gz | https://files.pythonhosted.org/packages/5a/82/42f767fc1c1143d6fd36efb827202a2d997a375e160a71eb2888a925aac1/pathspec-1.1.1.tar.gz | `17db5ecd524104a120e173814c90367a96a98d07c45b2e10c2f3919fff91bf5a` | 135,180 | 120 | 6 |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-win_arm64.whl | https://files.pythonhosted.org/packages/be/75/2432b3e3c7c62103b72d4c4cc8b16a56383ada372bbb0d1278591e988f71/playwright-1.63.0-py3-none-win_arm64.whl | `1e4a3a838ce22fb68ad17193fcd142a19610d9d70fb9966d2239f5dddc0cc05b` | 34,523,554 | 224 | 16 |
| strictyaml 1.7.3 | sdist | strictyaml-1.7.3.tar.gz | https://files.pythonhosted.org/packages/b3/08/efd28d49162ce89c2ad61a88bd80e11fb77bc9f6c145402589112d38f8af/strictyaml-1.7.3.tar.gz | `22f854a5fcab42b5ddba8030a0e4be51ca89af0267961c8d6cfa86395586c407` | 115,206 | 59 | 8 |
| ruff 0.14.14 | sdist | ruff-0.14.14.tar.gz | https://files.pythonhosted.org/packages/2e/06/f71e3a86b2df0dfa2d2f72195941cd09b44f87711cb7fa5193732cb9a5fc/ruff-0.14.14.tar.gz | `2d0f819c9a90205f3a867dbbd0be083bee9912e170fd7d9704cc8ae45824896b` | 4,515,732 | 4,737 | 45 |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-win_amd64.whl | https://files.pythonhosted.org/packages/76/eb/d6b8d92658038e260dbc7dd69fb3fdbe245aac283953de8b50b02bfe5f61/playwright-1.63.0-py3-none-win_amd64.whl | `2f9a707a6c6c91157ed77bff2b8caeb04b3c8d46e70d585fc134298cbe4b5cc6` | 38,606,082 | 224 | 16 |
| editables 0.5 | sdist | editables-0.5.tar.gz | https://files.pythonhosted.org/packages/37/4a/986d35164e2033ddfb44515168a281a7986e260d344cf369c3f52d4c3275/editables-0.5.tar.gz | `309627d9b5c4adc0e668d8c6fa7bac1ba7c8c5d415c2d27f60f081f8e80d1de2` | 14,744 | 18 | 3 |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-manylinux_2_17_aarch64.manylinux2014_aarch64.whl | https://files.pythonhosted.org/packages/f3/82/3d85505284c5a210f2da6c07b8f757524e79d1fba9cfdafe1eafb766ae59/playwright-1.63.0-py3-none-manylinux_2_17_aarch64.manylinux2014_aarch64.whl | `354e15b29503565fc598b89f16fbe070459343bef9d7498a93e304864000c6a7` | 47,902,708 | 224 | 15 |
| huggingface-hub 1.33.0 | sdist | huggingface_hub-1.33.0.tar.gz | https://files.pythonhosted.org/packages/25/2a/484d112c0d8fc5f665d7b65137ac9cdb2953c982391598c3597968a12ee7/huggingface_hub-1.33.0.tar.gz | `367be21a201db9523eddf8aeac7048f2602c1b308691c97640d5e72ed188007e` | 1,043,548 | 297 | 9 |
| python-dateutil 2.9.0.post0 | sdist | python-dateutil-2.9.0.post0.tar.gz | https://files.pythonhosted.org/packages/66/c0/0c8b6ad9f17a802ee498c46e004a0eb49bc148f2fd230864601a86dcf6db/python-dateutil-2.9.0.post0.tar.gz | `37dd54208da7e1cd875388217d5e00ebd4179249f90fb72437e91a35459a0ad3` | 342,432 | 113 | 8 |
| av 15.1.0 | sdist | av-15.1.0.tar.gz | https://files.pythonhosted.org/packages/e9/c3/83e6e73d1592bc54436eae0bc61704ae0cff0c3cfbde7b58af9ed67ebb49/av-15.1.0.tar.gz | `39cda2dc810e11c1938f8cb5759c41d6b630550236b3365790e67a313660ec85` | 3,774,192 | 360 | 23 |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-win_amd64.whl | https://files.pythonhosted.org/packages/87/44/90fa543014c45560cae1fffc63ea059fb3575ee6e1cb654562197e5d16fb/ruff-0.14.14-py3-none-win_amd64.whl | `3dde1435e6b6fe5b66506c1dff67a421d0b7f6488d466f651c07f4cab3bf20fd` | 11,630,486 | 7 | 5 |
| protobuf 7.36.2 | sdist | protobuf-7.36.2.tar.gz | https://files.pythonhosted.org/packages/d9/89/5b8517baa72f84a67b8a307ba953c91057af618bf40bf676f3c03551f8f0/protobuf-7.36.2.tar.gz | `497d0463ff3316681da6c0b9e8d06cb465d61abce00b613ab42226175644d1bb` | 512,737 | 331 | 7 |
| h11 0.16.0 | sdist | h11-0.16.0.tar.gz | https://files.pythonhosted.org/packages/01/ee/02a2c011bdab74c6fb3c75474d40b3052059d95df7e73351460c8588d963/h11-0.16.0.tar.gz | `4e35b956cf45792e4caa5885e69fba00bdbc6ffafbfa020300e549b208ee5ff1` | 101,250 | 69 | 8 |
| colorama 0.4.6 | wheel | colorama-0.4.6-py2.py3-none-any.whl | https://files.pythonhosted.org/packages/d1/d6/3965ed04c63042e047cb6a3e6ed1a63a35087b6a609aa3a15ed8ac56c221/colorama-0.4.6-py2.py3-none-any.whl | `4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6` | 25,335 | 17 | 4 |
| pygments 2.21.0 | sdist | pygments-2.21.0.tar.gz | https://files.pythonhosted.org/packages/49/2e/ced460408999b33da6b31b0021b0f37d329e202d4169aeb164493778f25b/pygments-2.21.0.tar.gz | `610ca751c9bc2492b38eb9a38a7fbc93edbbb2d7182edaf34e66ae493dee5c8c` | 5,005,329 | 2,797 | 7 |
| editables 0.5 | wheel | editables-0.5-py3-none-any.whl | https://files.pythonhosted.org/packages/6b/be/0f2f4a5e8adc114a02b63d92bf8edbfa24db6fc602fca83c885af2479e0e/editables-0.5-py3-none-any.whl | `61e5ffa82629e0d8bfe09bc44a07db3c1ab8ed1ce78a6980732870f19b5e7d4c` | 5,098 | 7 | 4 |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-win32.whl | https://files.pythonhosted.org/packages/69/8d/f74ff6b52751859f4b69caf66aa7d4a3c8d6c1f0c7dc9920da103612ee39/playwright-1.63.0-py3-none-win32.whl | `660c00c62639e31b16700ba5456b351ddba55bb766b7ce8261223aa34928e482` | 38,606,075 | 224 | 16 |
| iniconfig 2.3.1 | sdist | iniconfig-2.3.1.tar.gz | https://files.pythonhosted.org/packages/01/e1/2069291243c926a2ff1cd706c7f3eeb9b62144bf60f77c9fb9ff2fb26bd3/iniconfig-2.3.1.tar.gz | `67f4b9c50da0dedf52af349e7749a80a9057a5031199791b906c3bb3ae878960` | 21,209 | 32 | 7 |
| skills-ref 0.1.1 | sdist | skills_ref-0.1.1.tar.gz | https://files.pythonhosted.org/packages/23/42/943d3ba8b097af7068b7178563a5062ad8a977982f4a7b4f67facfc575e9/skills_ref-0.1.1.tar.gz | `6b400ca6e0049be62dca0167ff943ba2745fd67efb37fbba4d0ee341fccd2695` | 93,519 | 59 | 4 |
| httpcore 1.0.9 | sdist | httpcore-1.0.9.tar.gz | https://files.pythonhosted.org/packages/06/94/82699a10bca87a5556c9c59b5963f2d039dbd239f25bc2a63907a05a14cb/httpcore-1.0.9.tar.gz | `6e34463af53fd2ab5d807f399a9b45ea31c3dfa2276f15a2c3f00afff6e176e8` | 85,484 | 61 | 3 |
| certifi 2026.7.22 | sdist | certifi-2026.7.22.tar.gz | https://files.pythonhosted.org/packages/a3/c2/24167ea9858356b47a87a50d39908bfdb72ceeefe0041586e704e5376b3a/certifi-2026.7.22.tar.gz | `741e2c3b351ddf169a738da9f2c048608ff7f2c5cc02f1ebc6b118bb090d5d55` | 138,112 | 23 | 8 |
| httpx 0.28.1 | sdist | httpx-0.28.1.tar.gz | https://files.pythonhosted.org/packages/b1/df/48c586a5fe32a0f01324ee087459e112ebb7224f646c0b5023f5e79e9956/httpx-0.28.1.tar.gz | `75e98c5f16b0f35b567856f597f06ff2270a374470a5c2392242528e3e3e42fc` | 141,406 | 70 | 3 |
| flatbuffers 25.12.19 | wheel | flatbuffers-25.12.19-py2.py3-none-any.whl | https://files.pythonhosted.org/packages/e8/2d/d2a548598be01649e2d46231d151a6c56d10b964d94043a335ae56ea2d92/flatbuffers-25.12.19-py2.py3-none-any.whl | `7634f50c427838bb021c2d66a3d1168e9d199b0607e6329399f04846d42e20b4` | 26,661 | 14 | 3 |
| faster-whisper 1.2.1 | wheel | faster_whisper-1.2.1-py3-none-any.whl | https://files.pythonhosted.org/packages/05/99/49ee85903dee060d9f08297b4a342e5e0bcfca2f027a07b4ee0a38ab13f9/faster_whisper-1.2.1-py3-none-any.whl | `79a66ad50688c0b794dd501dc340a736992a6342f7f95e5811be60b5224a26a7` | 1,118,909 | 15 | 4 |
| pluggy 1.6.0 | sdist | pluggy-1.6.0.tar.gz | https://files.pythonhosted.org/packages/f9/e2/3e91f31a7d2b083fe6ef3fa267035b518369d9511ffab804f839851d2779/pluggy-1.6.0.tar.gz | `7dcc130b76258d33b90f61b658791dede3486c3e6bfb003ee5c9bfb396dd22f3` | 69,412 | 87 | 9 |
| tokenizers 0.23.2 | sdist | tokenizers-0.23.2.tar.gz | https://files.pythonhosted.org/packages/18/1e/bc6587c5ab643b2e17776cace9070a2ae73549c86bffac9934a600bf3c31/tokenizers-0.23.2.tar.gz | `7f0f085686b9de0d0079e6f874ae053600db64c5d13049e0bbc0119926d25aac` | 385,745 | 187 | 12 |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-macosx_10_13_x86_64.whl | https://files.pythonhosted.org/packages/19/dd/fbb3d34228ad753bc14464d5f2252585b73367539775a88d0a3949cf5a45/playwright-1.63.0-py3-none-macosx_10_13_x86_64.whl | `84c540759e8e7f01e690e197e04060f48899d37cea322299f255843273d3385d` | 44,278,407 | 224 | 15 |
| pytest 8.4.2 | sdist | pytest-8.4.2.tar.gz | https://files.pythonhosted.org/packages/a3/5c/00a0e072241553e1a7496d638deababa67c5058571567b92a7eaa258397c/pytest-8.4.2.tar.gz | `86c0d0b93306b961d58d62a4db4879f27fe25513d4b969df351abdddb3c30e01` | 1,519,618 | 698 | 8 |
| trove-classifiers 2026.9.21.13 | wheel | trove_classifiers-2026.9.21.13-py3-none-any.whl | https://files.pythonhosted.org/packages/30/81/0da8afb52a71d0a4f2bd3152357b1a441e393b286374802b9d3addab4ab5/trove_classifiers-2026.9.21.13-py3-none-any.whl | `8b1ff4f9c191b1040b71c37f1e445ab99732911e3cd91de52838453a854d7a17` | 14,232 | 9 | 5 |
| greenlet 3.5.6 | sdist | greenlet-3.5.6.tar.gz | https://files.pythonhosted.org/packages/3e/6e/0091f175ccd02b02bc8811bbcbcc6ac2e980be116e3b2f7a736ca322bf84/greenlet-3.5.6.tar.gz | `8e67c43bdfc88d5fee6db0d3e40175b362fc95fb85f0412d233b9b203c53a575` | 207,653 | 143 | 9 |
| packaging 26.3 | sdist | packaging-26.3.tar.gz | https://files.pythonhosted.org/packages/7d/fa/3944b40b07da9ce895c0e6303a5ab7d53da063554f534556b134a54d6093/packaging-26.3.tar.gz | `94edc256424af38762eb31306eed28beb9f0efc50a8837492c9d6fd6004aed79` | 313,412 | 105 | 9 |
| hatchling 1.27.0 | sdist | hatchling-1.27.0.tar.gz | https://files.pythonhosted.org/packages/8f/8a/cc1debe3514da292094f1c3a700e4ca25442489731ef7c0814358816bb03/hatchling-1.27.0.tar.gz | `971c296d9819abb3811112fc52c7a9751c8d381898f36533bb16f9791e941fd6` | 54,983 | 79 | 6 |
| ctranslate2 4.8.2 | wheel | ctranslate2-4.8.2-cp311-cp311-win_amd64.whl | https://files.pythonhosted.org/packages/7e/86/21926da682103a20d4f4833b389131b801c71e6b8d6047be5f0a28fe673a/ctranslate2-4.8.2-cp311-cp311-win_amd64.whl | `995938fcd24a1174a7abf9765e7fa216b5b91a1d8e8c4c8f383c7a186e8bab2e` | 19,220,522 | 33 | 8 |
| anyio 4.15.1 | sdist | anyio-4.15.1.tar.gz | https://files.pythonhosted.org/packages/a9/d2/f4d173e22df740bc37b1db102b386ba719b66e95b0f0d751f556b387e6d2/anyio-4.15.1.tar.gz | `9f28306018cbd6d329e64a36d58256edff76dd996fe423bc957326e578b82a94` | 276,966 | 144 | 7 |
| pathspec 1.1.1 | wheel | pathspec-1.1.1-py3-none-any.whl | https://files.pythonhosted.org/packages/f1/d9/7fb5aa316bc299258e68c73ba3bddbc499654a07f151cba08f6153988714/pathspec-1.1.1-py3-none-any.whl | `a00ce642f577bf7f473932318056212bc4f8bfdf53128c78bbd5af0b9b20b189` | 57,328 | 36 | 4 |
| idna 3.20 | sdist | idna-3.20.tar.gz | https://files.pythonhosted.org/packages/f5/08/8eea9d4b8302028f3abb2c0813953f7aec26d33b7a8960ed760e65ff29fa/idna-3.20.tar.gz | `a7db850025b95ded1eae8a46181a1a6c56c92c96f0e2b005d9ff8dc0210cab44` | 216,463 | 31 | 3 |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-manylinux1_x86_64.whl | https://files.pythonhosted.org/packages/27/9c/103a5037789062bdab27c7dca53f3ca6b075b572ab2cd96eec825b3aec4e/playwright-1.63.0-py3-none-manylinux1_x86_64.whl | `ad21bc07516b187965a7521c5cf0df0bd657b17482eaad74335272d35a2b07de` | 48,217,159 | 224 | 15 |
| click 8.5.0 | sdist | click-8.5.0.tar.gz | https://files.pythonhosted.org/packages/c7/0e/7fa0ef50764b67090eca4114772a2abf8b6148198475e54c660b97caeee6/click-8.5.0.tar.gz | `ba0d2089de75ea0310e2dde03160e6ca10009947fb95a182f9b54021bb272e34` | 382,235 | 112 | 4 |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-macosx_11_0_universal2.whl | https://files.pythonhosted.org/packages/94/11/dc5c13fa1602371603acd461be47529c1b3513815d3a0dc98f642c291a10/playwright-1.63.0-py3-none-macosx_11_0_universal2.whl | `c89fc4736502a1f0fac2c8ca5d10c0cbc1c669f1f4774a2d8507a43140e4d53f` | 44,278,410 | 224 | 15 |
| tqdm 4.70.1 | sdist | tqdm-4.70.1.tar.gz | https://files.pythonhosted.org/packages/0d/ea/b2a5bd54b28a324dae8211928b2d730b6547500342c7e6c6dea08bd0a485/tqdm-4.70.1.tar.gz | `cefd0eca11b2a37a3aee776544d4f4ae913f02688135b5556b8788dfa474afc4` | 171,846 | 96 | 7 |
| filelock 4.0.12 | sdist | filelock-4.0.12.tar.gz | https://files.pythonhosted.org/packages/53/e4/34efcb869715cf299e47d1ac7b2624d2bcb6f2d3dffc2f0abe8417f65ab2/filelock-4.0.12.tar.gz | `cf42711a7ac791818b299fab0332a088c65aeeefa36290de98db92c434303b0c` | 253,880 | 88 | 3 |
| hf-xet 1.7.0 | sdist | hf_xet-1.7.0.tar.gz | https://files.pythonhosted.org/packages/9e/27/06d899ea7bd721d272f84aac98bdb238de98af4cc767a69056d967d68c71/hf_xet-1.7.0.tar.gz | `d406ec79053c0871817f700c2ac8c36ba0d87f9c34b7458b0f0063bb218b0466` | 985,689 | 400 | 12 |
| pyyaml 6.0.3 | sdist | pyyaml-6.0.3.tar.gz | https://files.pythonhosted.org/packages/05/8e/961c0007c59b8dd7729d542c61a4d537767a59645b82a0b521206e1e25c2/pyyaml-6.0.3.tar.gz | `d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f` | 130,960 | 656 | 8 |
| typing-extensions 4.16.0 | sdist | typing_extensions-4.16.0.tar.gz | https://files.pythonhosted.org/packages/f6/cc/6253133b5bb138fc3306cebfbda2c520f545d36b5be2c7255cc528bb45d6/typing_extensions-4.16.0.tar.gz | `dc983d19a509c94dba722ee6abd33940f7c05a89e243c47e907eb4db6f1a43e5` | 113,555 | 9 | 3 |
| numpy 2.5.3 | sdist | numpy-2.5.3.tar.gz | https://files.pythonhosted.org/packages/13/01/11703282db468b85f6f7b8c7f22d058de5970d5c7e60a3a8aaa313c3de36/numpy-2.5.3.tar.gz | `df2d5874ff183595a4ba404edd04f6bd9b5505c1d7708573f6a6c17489a67563` | 20,791,231 | 8,367 | 165 |
| onnxruntime 1.30.0 | wheel | onnxruntime-1.30.0-cp312-cp312-win_amd64.whl | https://files.pythonhosted.org/packages/a6/13/0f1699f6de549c9324bc9112a2a85b14c517904cd11b562a654643b755a1/onnxruntime-1.30.0-cp312-cp312-win_amd64.whl | `f3501472571f1b1eee50e017851e7929f5ea37312d2d8c2494a19e8fc58b4a38` | 14,311,470 | 323 | 13 |
| numpy 2.4.6 | sdist | numpy-2.4.6.tar.gz | https://files.pythonhosted.org/packages/d0/ad/fed0499ce6a338d2a03ebae59cd15093910c8875328855781952abf6c2fe/numpy-2.4.6.tar.gz | `f3a3570c4a2a16746ac2c31a7c7c7b0c186b95ce902e33db6f28094ed7387dda` | 20,735,807 | 8,250 | 146 |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-macosx_11_0_arm64.whl | https://files.pythonhosted.org/packages/f5/9a/948b930b1a8c4ee869e5a139a2b7747caa06aab56a3f09a2f0abdcbda221/playwright-1.63.0-py3-none-macosx_11_0_arm64.whl | `fd1aa00631d44d55e56e0975bf3f3f285fac4a9fd2813183f0c12a488f1a1b24` | 42,944,679 | 224 | 15 |
| six 1.17.0 | sdist | six-1.17.0.tar.gz | https://files.pythonhosted.org/packages/94/e7/b2c673351809dca68a0e064b6af791aa332cf192da575fd474ed7d6f16a2/six-1.17.0.tar.gz | `ff70335d468e7eb6ec65b95b99d3a2836546063f63acc5171de367e834932a81` | 34,031 | 19 | 7 |

## Candidate flag counts

These counts are per member row; a member can carry more than one flag.

| Candidate label | Member rows |
|---|---:|
| `dependency-metadata-name` | 492 |
| `license-notice-name` | 196 |
| `native-binary-extension` | 62 |
| `native-dependency-name` | 36 |

## Candidate flag meanings

- `license-notice-name`: member path contains `LICENSE`, `LICENCE`, `NOTICE`, `COPYING`, or a `THIRD-PARTY` spelling.
- `native-binary-extension`: member suffix is a common native/binary extension (`.dll`, `.pyd`, `.so`, `.dylib`, `.a`, `.lib`, `.exe`, `.node`, `.wasm`, or related entries in the scanner).
- `native-dependency-name`: the member filename contains a known native-library name such as FFmpeg/libav, x264/x265, OpenBLAS, cuDNN, OpenMP, ONNX Runtime, CTranslate2, Tokenizers, or MKL.
- `dependency-metadata-name`: the member filename is a package/build/dependency metadata name such as `METADATA`, `PKG-INFO`, `RECORD`, `Cargo.lock`, `package.json`, `pyproject.toml`, or a `.cmake`/`.pc` file.

## Limits

This scan lists cached lock-pinned archive members and labels names/paths that merit later review. It does not inspect file contents, enumerate binaries' linked dependencies, prove build inputs, decide which dependencies are shipped, or draw any `licenseConcluded` value. The separate project distribution-scope and license-owner decisions remain open.
