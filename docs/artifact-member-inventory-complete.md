# Bounded full-lock artifact member inventory

## Coverage and method

- Lock SHA-256: f4fc838d6f52555ca03ccf378c67e2a988666928904ff14bfab6d4af7c88f31b.
- Unique lock artifacts expected: 235; scanned: 235; failed at an archive safety bound: 0; not scanned due to global budget: 0.
- Scanned artifacts total 2,097,567,472 compressed bytes and 6,531,851,175 archive bytes traversed/declared. The run used a 17,179,869,184-byte aggregate expanded-byte budget and took 10.9 seconds.
- Member rows: 86,827; candidate member rows: 6,239. Candidate flag counts are per row, and one row may carry multiple flags.
- The existing bounded archive reader checked each selected artifact against the lock and listed ZIP/tar members in place. No archive member was extracted, imported, installed, or executed.
- Candidate labels are path/name heuristics. This inventory does not hash member contents, prove the complete native BOM or build provenance, determine license applicability, or approve redistribution.

## Member detail

The complete JSONL rows are partitioned into these files (each part is capped at 8 MiB):

- [artifact-member-inventory-complete-part-001.jsonl](artifact-member-inventory-complete-part-001.jsonl) — 39,821 rows, 8,388,517 bytes, SHA-256 d06ca8eea88114ea86b320de644738cd9447b3b9e45c7c672a789d00a7ed1098.
- [artifact-member-inventory-complete-part-002.jsonl](artifact-member-inventory-complete-part-002.jsonl) — 39,230 rows, 8,388,384 bytes, SHA-256 5234e00063624366774147ad38be91cbf46241027018f518e7ce7cd8d5c20a67.
- [artifact-member-inventory-complete-part-003.jsonl](artifact-member-inventory-complete-part-003.jsonl) — 7,776 rows, 1,737,591 bytes, SHA-256 6e288088d473604a8100e84d9f15676c8d0af884ce86ead5d380ee41c47ed341.

## Artifact results

| Package/version | Type | Filename | SHA-256 | Bytes | Members | Candidate members | Expanded bytes walked | Status |
|---|---|---|---|---:|---:|---:|---:|---|
| onnxruntime 1.30.0 | wheel | onnxruntime-1.30.0-cp312-cp312-macosx_14_0_arm64.whl | 001ed726c9bd5e2bc92faade7d37d889e9606a350b7d5529f0227df2e3bb57fd | 21,544,867 | 352 | 14 | 78,198,332 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp312-cp312-macosx_10_13_x86_64.whl | 001fbb8e08d942dd57599e781f2472269ee7f2755fae407b4f67b2f0b17da3f1 | 16,689,119 | 1,033 | 81 | 55,745,287 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl | 01ff589aab3f5b539e35db38425da31a57521efd1e4ad1ae08fc34dbe30bd7df | 12,005,701 | 7 | 4 | 28,507,834 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-macosx_11_0_arm64.whl | 026c1d25996818f0bf498636686199d9bd0d9d6341c9c2c3b62e2a0198b758de | 10,231,273 | 7 | 4 | 23,377,913 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp311-cp311-macosx_10_9_x86_64.whl | 0280e0356c0829a18d9de1cb7eee50ec22ca639878d7240307ca0943d73cd2c4 | 16,969,194 | 1,167 | 81 | 56,617,502 | scanned |
| huggingface-hub 1.33.0 | wheel | huggingface_hub-1.33.0-py3-none-any.whl | 04e434b06e100eddbce9a6e817d72693a7884b10a79bd67ab48080d5c07eb899 | 846,435 | 194 | 5 | 3,291,113 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp312-cp312-musllinux_1_2_aarch64.whl | 0616b8f878098c5681fd8f0dc92d887551717402342a70f0abcbfea5f5ad8a44 | 1,584,998 | 111 | 11 | 6,308,902 | scanned |
| colorama 0.4.6 | sdist | colorama-0.4.6.tar.gz | 08695f5cb7ed6e0531a20572697297273c47b8cae5a63ffc6d6ed5c201be6e44 | 27,697 | 31 | 3 | 143,360 | scanned |
| av 15.1.0 | wheel | av-15.1.0-cp311-cp311-musllinux_1_2_aarch64.whl | 08eac47a90ebae1e2bd5935f400dd515166019bab4ff5b03c4625fa6ac3a0a5e | 40,112,634 | 278 | 102 | 101,293,451 | scanned |
| numpy 2.5.3 | wheel | numpy-2.5.3-cp312-cp312-win_amd64.whl | 0a59a421a32580a009e8a1751345bf829631b990dc1794b80514ab722b435def | 12,567,828 | 1,062 | 98 | 41,918,931 | scanned |
| hf-xet 1.7.0 | wheel | hf_xet-1.7.0-cp38-abi3-musllinux_1_2_x86_64.whl | 0a9e802f33bf50c851abe45fc5380e61f959e2d369647d6742b79ad9d6c27cab | 4,418,814 | 8 | 6 | 12,109,550 | scanned |
| trove-classifiers 2026.9.21.13 | sdist | trove_classifiers-2026.9.21.13.tar.gz | 0a9ebc8d4e2f3e8a22848c5258033035bec17a3012ac3fea16dbaa764489eb71 | 17,085 | 32 | 9 | 133,120 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp311-cp311-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl | 0ab0a9c4ffb1a6d95ef519fe4247dba8eb6b18ad93999f76b7f657039acabd47 | 15,966,692 | 1,165 | 79 | 55,772,341 | scanned |
| pyee 13.0.1 | sdist | pyee-13.0.1.tar.gz | 0b931f7c14535667ed4c7e0d531716368715e860b988770fc7eb8578d1f67fc8 | 31,655 | 54 | 7 | 215,040 | scanned |
| onnxruntime 1.30.0 | wheel | onnxruntime-1.30.0-cp311-cp311-win_amd64.whl | 0edd0145a6e3fce8a1276491dc784d615e3c58bcb952c9b4e5c876d5c6a12ad7 | 14,309,136 | 323 | 13 | 41,831,575 | scanned |
| fsspec 2026.9.0 | sdist | fsspec-2026.9.0.tar.gz | 0f08147951c8cb31d844c3547d631053b127863b60be04cf06e121333ee0e2fe | 333,545 | 93 | 5 | 1,136,640 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp311-cp311-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl | 10892704fc220243f5305762e276552a0395f7beb4dbf9b14ec8fd43b57f126c | 775,556 | 28 | 6 | 2,909,372 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp311-cp311-macosx_11_0_arm64.whl | 110f8b71aacb688ec69062bb7f6938a0f8acb01b7c1c4beb453c65b6d234584d | 14,964,111 | 1,167 | 81 | 49,882,387 | scanned |
| av 15.1.0 | wheel | av-15.1.0-cp312-cp312-manylinux_2_28_x86_64.whl | 11326f197e7001c4ca53a83b2dbc67fd39ddff8cdf62ce6be3b22d9f3f9338bd | 39,915,519 | 274 | 98 | 118,323,728 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-manylinux_2_31_riscv64.whl | 12f0835dc2ee694746a76adf7b1567d4346a4a502ebe93fb1f5f80ea49799b78 | 3,577,314 | 32 | 7 | 11,191,665 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-manylinux_2_31_riscv64.whl | 14649acb1cf7b5d2d283ebd2f58d56b75836ed8c6f329664fa91cdea19e76e66 | 11,180,549 | 7 | 4 | 24,233,838 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-manylinux_2_17_i686.manylinux2014_i686.whl | 1629e67489c2dea43e8658c3dba659edbfd87361624b4040d1df04c9740ae906 | 11,043,637 | 7 | 4 | 25,924,368 | scanned |
| onnxruntime 1.30.0 | wheel | onnxruntime-1.30.0-cp311-cp311-win_arm64.whl | 16506cfa5d218850f2b46e0edce1b952121f2f84f8e0074dafe15f4787f0c8fb | 14,167,408 | 323 | 13 | 42,339,007 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-musllinux_1_2_x86_64.whl | 16bc890fb4cc9781bb05beb5ab4cd51be9e7cb376bf1dd3580512b24eb3fda2b | 11,315,626 | 7 | 4 | 27,774,956 | scanned |
| pathspec 1.1.1 | sdist | pathspec-1.1.1.tar.gz | 17db5ecd524104a120e173814c90367a96a98d07c45b2e10c2f3919fff91bf5a | 135,180 | 120 | 6 | 1,085,440 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp311-cp311-musllinux_1_2_x86_64.whl | 188bf333769b7145e2b0b4a7f09615ec550ed44d3a2a8395fb7b36f0e9901e13 | 1,653,119 | 111 | 11 | 5,942,132 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp311-cp311-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl | 1c20ea32a73d17b9b60e3371240e17b0068120c98a5ec01a224a7dd8c89733ba | 624,428 | 106 | 9 | 2,082,096 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-manylinux_2_17_s390x.manylinux2014_s390x.whl | 1cc12d74eef0f29f51775f5b755913eb523546b88e2d733e1d701fe65144e89b | 11,282,455 | 7 | 4 | 27,983,102 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp311-cp311-musllinux_1_2_aarch64.whl | 1d37d57ad971609cf3c53ba6a7e365e40660e3be0e5175fa9f2365a379d6095a | 767,463 | 28 | 6 | 2,149,509 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp311-cp311-win_amd64.whl | 1e254a00cdf42b1e4d5b3d68d33af63268d41340d8885df2ab6470f2e1500147 | 12,608,406 | 1,184 | 98 | 41,811,329 | scanned |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-win_arm64.whl | 1e4a3a838ce22fb68ad17193fcd142a19610d9d70fb9966d2239f5dddc0cc05b | 34,523,554 | 224 | 16 | 97,962,451 | scanned |
| strictyaml 1.7.3 | sdist | strictyaml-1.7.3.tar.gz | 22f854a5fcab42b5ddba8030a0e4be51ca89af0267961c8d6cfa86395586c407 | 115,206 | 59 | 8 | 747,520 | scanned |
| pygments 2.21.0 | wheel | pygments-2.21.0-py3-none-any.whl | 2363c69b61c4a97c838da3b130dcd6468f4848992b21a82f2a63ec34377137d9 | 1,250,147 | 349 | 6 | 4,621,166 | scanned |
| click 8.5.0 | wheel | click-8.5.0-py3-none-any.whl | 255bc9599cf7748b4b1a446ccc735421bd08a2ae529a8b88597d3de5664ee360 | 125,251 | 22 | 4 | 447,719 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-manylinux_2_17_ppc64.manylinux2014_ppc64.whl | 27493a2131ea0f899057d49d303e4292b2cae2bb57253c1ed1f256fbcd1da480 | 12,194,761 | 7 | 4 | 29,359,894 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-pp311-pypy311_pp73-win_amd64.whl | 2803abfebfc990042cd494d8ce2d5f82e9d847af6d35ec486923aa19dbad5e73 | 12,504,263 | 1,185 | 99 | 41,559,835 | scanned |
| hf-xet 1.7.0 | wheel | hf_xet-1.7.0-cp38-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl | 2814a6e999d13464c4d679b788cc5d784eb5a4edfc638a31f10e9a11ab531ef8 | 4,212,180 | 7 | 5 | 11,573,549 | scanned |
| hf-xet 1.7.0 | wheel | hf_xet-1.7.0-cp38-abi3-win_amd64.whl | 2b7bb5727889b0f2436dbaaad8fc4c3e66b8240d992716989e0c086b4278b1bc | 3,822,644 | 7 | 5 | 9,664,133 | scanned |
| av 15.1.0 | wheel | av-15.1.0-cp311-cp311-manylinux_2_28_aarch64.whl | 2b9623ae848625c59213b610c8665817924f913580c7c5c91e0dc18936deb00d | 38,062,118 | 273 | 97 | 111,367,335 | scanned |
| ruff 0.14.14 | sdist | ruff-0.14.14.tar.gz | 2d0f819c9a90205f3a867dbbd0be083bee9912e170fd7d9704cc8ae45824896b | 4,515,732 | 4,737 | 45 | 34,681,856 | scanned |
| httpcore 1.0.9 | wheel | httpcore-1.0.9-py3-none-any.whl | 2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55 | 78,784 | 36 | 4 | 288,016 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-win_amd64.whl | 2e96f5699d5249c9c64aa8412e044f727aae3a4098cf830f9901ec1afc361cde | 2,863,236 | 32 | 7 | 8,240,520 | scanned |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-win_amd64.whl | 2f9a707a6c6c91157ed77bff2b8caeb04b3c8d46e70d585fc134298cbe4b5cc6 | 38,606,082 | 224 | 16 | 109,661,139 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp312-cp312-win_arm64.whl | 301102a49120b095e72a7838792b41233975fc1c155daec6d98f81c00c9280e0 | 308,310 | 99 | 8 | 856,815 | scanned |
| editables 0.5 | sdist | editables-0.5.tar.gz | 309627d9b5c4adc0e668d8c6fa7bac1ba7c8c5d415c2d27f60f081f8e80d1de2 | 14,744 | 18 | 3 | 81,920 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp312-cp312-macosx_14_0_arm64.whl | 3213d622a0283a39a93d188f3cf72b26862df52fbb4ca3697f51705016523d41 | 5,204,410 | 1,028 | 77 | 19,513,892 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl | 325fee2e0418a9dc6c9ecf736a5f5f0db7875183ace9549ae339da76f7a1fbb7 | 4,024,165 | 32 | 7 | 13,111,335 | scanned |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-manylinux_2_17_aarch64.manylinux2014_aarch64.whl | 354e15b29503565fc598b89f16fbe070459343bef9d7498a93e304864000c6a7 | 47,902,708 | 224 | 15 | 138,971,793 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp312-cp312-macosx_14_0_x86_64.whl | 357cc07a6d7b0b182ff02249616a03742827ebb1277546b5c7cd7f7620a45698 | 6,551,240 | 1,028 | 77 | 23,221,994 | scanned |
| huggingface-hub 1.33.0 | sdist | huggingface_hub-1.33.0.tar.gz | 367be21a201db9523eddf8aeac7048f2602c1b308691c97640d5e72ed188007e | 1,043,548 | 297 | 9 | 5,509,120 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp311-cp311-musllinux_1_2_x86_64.whl | 37503bfbfc9d2c40b344d06b2199cf0e96e97957ab1c1b546fd4f87e53e5d3e4 | 794,986 | 28 | 6 | 2,089,715 | scanned |
| python-dateutil 2.9.0.post0 | sdist | python-dateutil-2.9.0.post0.tar.gz | 37dd54208da7e1cd875388217d5e00ebd4179249f90fb72437e91a35459a0ad3 | 342,432 | 113 | 8 | 1,280,000 | scanned |
| ctranslate2 4.8.2 | wheel | ctranslate2-4.8.2-cp311-cp311-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl | 3823c9883c2c410a76b2f19feda9da628a3c112cedfd912db815e0055c8235e2 | 16,720,002 | 38 | 10 | 64,945,764 | scanned |
| av 15.1.0 | sdist | av-15.1.0.tar.gz | 39cda2dc810e11c1938f8cb5759c41d6b630550236b3365790e67a313660ec85 | 3,774,192 | 360 | 23 | 25,845,760 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-manylinux_2_17_armv7l.manylinux2014_armv7l.whl | 3c0f18b922c6d2ff9a5e6c3ee16259adc513ca775bcf82c67ebab7cbd9da5bc8 | 10,286,052 | 7 | 4 | 22,606,792 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp311-cp311-manylinux_2_24_ppc64le.manylinux_2_28_ppc64le.whl | 3c6dede9133e1da41d561bc3fb14e92b47e2ce39ae60edefaad145658ea7c5e2 | 625,405 | 106 | 9 | 2,572,875 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp312-cp312-musllinux_1_2_x86_64.whl | 3dbb4596a6a4e5d47121a33ff20533a81e60f302d9e67b69909a8bc21a43f0a7 | 1,647,568 | 111 | 11 | 5,929,852 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-win_amd64.whl | 3dde1435e6b6fe5b66506c1dff67a421d0b7f6488d466f651c07f4cab3bf20fd | 11,630,486 | 7 | 5 | 31,832,299 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp312-cp312-win_arm64.whl | 4081eb135ac24158bd51cdfbef16f1c64df7063b1143f24731387137c092bec8 | 10,221,482 | 1,050 | 98 | 29,907,092 | scanned |
| av 15.1.0 | wheel | av-15.1.0-cp312-cp312-macosx_13_0_arm64.whl | 40c5df37f4c354ab8190c6fd68dab7881d112f527906f64ca73da4c252a58cee | 21,760,991 | 260 | 84 | 56,135,039 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp312-cp312-musllinux_1_2_x86_64.whl | 41715c910c881bc081f1e8872880d3c650acf13dfa8214bad49ed4cede7c34ea | 790,181 | 28 | 6 | 2,116,395 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl | 41c2f84d172449b4dadb9cdc508e3e364076613c35b16e76ecfe47a60d1e3305 | 3,386,843 | 32 | 7 | 11,701,061 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-manylinux_2_17_i686.manylinux2014_i686.whl | 43e4f2071e3cc8d5d86421c874aebc82659bb51a68bcdef5a0da75ee89511ccb | 3,748,165 | 32 | 7 | 11,347,509 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp311-cp311-macosx_10_13_x86_64.whl | 44edc647873928551a01e7a563d7452ccdebee747728c1080d881d68af7b997e | 185,826 | 28 | 6 | 606,625 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp311-cp311-manylinux_2_24_aarch64.manylinux_2_28_aarch64.whl | 45bfd2b51e38aaa5f9849f114d9c7c1d75f69187c849b3549cd64c465283abfa | 613,429 | 106 | 9 | 2,498,943 | scanned |
| six 1.17.0 | wheel | six-1.17.0-py2.py3-none-any.whl | 4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274 | 11,050 | 6 | 4 | 37,975 | scanned |
| typing-extensions 4.16.0 | wheel | typing_extensions-4.16.0-py3-none-any.whl | 481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8 | 45,571 | 5 | 4 | 182,767 | scanned |
| protobuf 7.36.2 | sdist | protobuf-7.36.2.tar.gz | 497d0463ff3316681da6c0b9e8d06cb465d61abce00b613ab42226175644d1bb | 512,737 | 331 | 7 | 4,126,720 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp311-cp311-macosx_14_0_arm64.whl | 4cfe66903cc32a9921a6733d96b19bb6abf310397581bbad89c228f5abaf0ee8 | 5,469,159 | 1,162 | 77 | 20,357,588 | scanned |
| h11 0.16.0 | sdist | h11-0.16.0.tar.gz | 4e35b956cf45792e4caa5885e69fba00bdbc6ffafbfa020300e549b208ee5ff1 | 101,250 | 69 | 8 | 471,040 | scanned |
| colorama 0.4.6 | wheel | colorama-0.4.6-py2.py3-none-any.whl | 4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6 | 25,335 | 17 | 4 | 77,669 | scanned |
| numpy 2.5.3 | wheel | numpy-2.5.3-cp312-cp312-musllinux_1_2_aarch64.whl | 4f8929ee6c96bfbd7b4ed2032e0c03af86fe1826740ab61ddabf9072d06e57ff | 17,040,975 | 1,048 | 82 | 57,990,048 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp311-cp311-manylinux_2_24_s390x.manylinux_2_28_s390x.whl | 4fb8e59f68845d56c23c031dcd79c329f345e4a9d2ffac91c3d1ab366bdc457b | 633,270 | 106 | 9 | 2,061,259 | scanned |
| ctranslate2 4.8.2 | wheel | ctranslate2-4.8.2-cp312-cp312-macosx_11_0_x86_64.whl | 5385f15493e7b6f41377da83d0d5afeb8e0f36188260722f3800c3c7121455af | 11,931,717 | 38 | 9 | 61,465,931 | scanned |
| ctranslate2 4.8.2 | wheel | ctranslate2-4.8.2-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl | 554a0b2abf098a11c66ef7930c0a05b3de683a455e8ea3f2e6ab6966aaabc136 | 39,555,908 | 38 | 10 | 140,077,994 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-pp311-pypy311_pp73-macosx_10_15_x86_64.whl | 55cced7c52e981362f708ad635198e97a752dfba412cc03c23bbf3bd8d5cd662 | 16,847,511 | 1,167 | 81 | 56,367,368 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-win_arm64.whl | 56e6981a98b13a32236a72a8da421d7839221fa308b223b9283312312e5ac76c | 10,920,448 | 7 | 5 | 26,288,875 | scanned |
| av 15.1.0 | wheel | av-15.1.0-cp311-cp311-win_amd64.whl | 57b99544d91121b8bea570e4ddf61700f679a6b677c1f37966bc1a22e1d4cd5c | 31,335,683 | 266 | 90 | 88,049,793 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp311-cp311-win_arm64.whl | 59deccd347735a7774223b05a93773fddbb298aba3cea21be4337fb4752dbe32 | 307,739 | 99 | 8 | 855,279 | scanned |
| hf-xet 1.7.0 | wheel | hf_xet-1.7.0-cp38-abi3-macosx_11_0_arm64.whl | 59fba37039233c7fcbe196817d6cdcf1b40dfb17b410f229d85b0cf0a1848da4 | 3,560,352 | 7 | 5 | 7,713,595 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp311-cp311-musllinux_1_2_aarch64.whl | 5a0b2791239c99992a86c1b635b787fe2a877d9eaaa26f8891ce943832b585ae | 1,588,385 | 111 | 11 | 6,374,430 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-musllinux_1_2_x86_64.whl | 5c56bda1511921587789163e524d196ed8284174ac23abd7685d5ea8da6c4718 | 10,256,304 | 34 | 9 | 30,427,135 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-pp311-pypy311_pp73-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl | 5dbbdb29840ca3d91ee0fece42fc29278886d908280bfec0a5846c6f901a3eb0 | 15,798,374 | 1,165 | 79 | 55,369,490 | scanned |
| filelock 4.0.12 | wheel | filelock-4.0.12-py3-none-any.whl | 5f17ee83ecee8a6f3e389c75822fb70a1c2f0506b99438a6dffa1d56793588c8 | 111,732 | 28 | 4 | 389,423 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl | 5f9fb9157b4ce2971008323afe46053787b526ef624fea915b261468a8421a0f | 15,671,012 | 1,031 | 79 | 54,892,173 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp312-cp312-win_amd64.whl | 5fcd34e47f6e0b794d17de1b4ff496c00986e1c83f7ab2fb8fcfe9616ff7477b | 154,003 | 24 | 5 | 478,269 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp312-cp312-manylinux2014_s390x.manylinux_2_17_s390x.manylinux_2_28_s390x.whl | 5fdec68f91a0c6739b380c83b951e2c72ac0197ace422360e6d5a959d8d97b2c | 844,011 | 28 | 6 | 3,004,540 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-macosx_10_12_x86_64.whl | 6006a0082336e7920b9573ef8a7f52eec837add1265cc74e04ea8a4368cd704c | 10,883,245 | 7 | 4 | 25,650,735 | scanned |
| pygments 2.21.0 | sdist | pygments-2.21.0.tar.gz | 610ca751c9bc2492b38eb9a38a7fbc93edbbb2d7182edaf34e66ae493dee5c8c | 5,005,329 | 2,797 | 7 | 47,564,800 | scanned |
| anyio 4.15.1 | wheel | anyio-4.15.1-py3-none-any.whl | 6152fdbbf9a77fdec97731721bebf7c4c44f7c29b424b0065826173efc7ed101 | 132,079 | 53 | 5 | 539,217 | scanned |
| editables 0.5 | wheel | editables-0.5-py3-none-any.whl | 61e5ffa82629e0d8bfe09bc44a07db3c1ab8ed1ce78a6980732870f19b5e7d4c | 5,098 | 7 | 4 | 9,931 | scanned |
| certifi 2026.7.22 | wheel | certifi-2026.7.22-py3-none-any.whl | 62f22742b58a1a33014a2b6b706588a8d7e2a88ae7bd1a6ebe8c992928483775 | 136,983 | 12 | 4 | 248,921 | scanned |
| h11 0.16.0 | wheel | h11-0.16.0-py3-none-any.whl | 63cf8bbe7522de3bf65932fda1d9c2772064ffb3dae62d55932da54b31cb6c86 | 37,515 | 17 | 4 | 103,935 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp312-cp312-win_arm64.whl | 64386e5e707d03a7e172c0701abfb7e10f0fb753ee1d773128192742712a98fd | 140,344 | 24 | 5 | 493,117 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp311-cp311-macosx_11_0_arm64.whl | 652cb6edd41e718550aad172851962662ff2681490a8a711af6a4d288dd96824 | 175,577 | 28 | 6 | 608,151 | scanned |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-win32.whl | 660c00c62639e31b16700ba5456b351ddba55bb766b7ce8261223aa34928e482 | 38,606,075 | 224 | 16 | 109,661,135 | scanned |
| iniconfig 2.3.1 | sdist | iniconfig-2.3.1.tar.gz | 67f4b9c50da0dedf52af349e7749a80a9057a5031199791b906c3bb3ae878960 | 21,209 | 32 | 7 | 133,120 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-pp311-pypy311_pp73-macosx_14_0_arm64.whl | 68a5124b13fa6cc2086764a20005d30bc0548146f7f5322f02fce212ca14317f | 5,394,157 | 1,162 | 77 | 20,187,862 | scanned |
| skills-ref 0.1.1 | sdist | skills_ref-0.1.1.tar.gz | 6b400ca6e0049be62dca0167ff943ba2745fd67efb37fbba4d0ee341fccd2695 | 93,519 | 59 | 4 | 327,680 | scanned |
| onnxruntime 1.30.0 | wheel | onnxruntime-1.30.0-cp312-cp312-manylinux_2_28_aarch64.whl | 6c32a000d5139a38ba9349030b0032e3331acb559d596b22738d9d2b343a2b83 | 21,345,202 | 353 | 15 | 55,701,456 | scanned |
| httpcore 1.0.9 | sdist | httpcore-1.0.9.tar.gz | 6e34463af53fd2ab5d807f399a9b45ea31c3dfa2276f15a2c3f00afff6e176e8 | 85,484 | 61 | 3 | 552,960 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp312-cp312-manylinux_2_39_riscv64.whl | 71890d5247020c25c21a6b65202782bfc281d4e6e244842419d30e3492bb6dcc | 432,385 | 106 | 9 | 1,232,740 | scanned |
| certifi 2026.7.22 | sdist | certifi-2026.7.22.tar.gz | 741e2c3b351ddf169a738da9f2c048608ff7f2c5cc02f1ebc6b118bb090d5d55 | 138,112 | 23 | 8 | 296,960 | scanned |
| httpx 0.28.1 | sdist | httpx-0.28.1.tar.gz | 75e98c5f16b0f35b567856f597f06ff2270a374470a5c2392242528e3e3e42fc | 141,406 | 70 | 3 | 911,360 | scanned |
| flatbuffers 25.12.19 | wheel | flatbuffers-25.12.19-py2.py3-none-any.whl | 7634f50c427838bb021c2d66a3d1168e9d199b0607e6329399f04846d42e20b4 | 26,661 | 14 | 3 | 87,988 | scanned |
| numpy 2.5.3 | wheel | numpy-2.5.3-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl | 76c2c1e6bfa5c84adc6434dfbf013aa92096a7985221762c8f11fedfd20fff58 | 15,687,872 | 1,043 | 79 | 54,272,416 | scanned |
| ctranslate2 4.8.2 | wheel | ctranslate2-4.8.2-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl | 781f835da7fdc4adcc38f9d674dbe9b37eaf3c9aee3b2bc17d684342ff59d549 | 16,894,628 | 38 | 10 | 65,797,692 | scanned |
| faster-whisper 1.2.1 | wheel | faster_whisper-1.2.1-py3-none-any.whl | 79a66ad50688c0b794dd501dc340a736992a6342f7f95e5811be60b5224a26a7 | 1,118,909 | 15 | 4 | 1,382,109 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp312-cp312-win_amd64.whl | 7ac4abb3877c43af320392c664774eef6fa2cc063c79a55fc02d844a3cbe7395 | 324,203 | 99 | 8 | 860,399 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-manylinux_2_17_armv7l.manylinux2014_armv7l.whl | 7b7e37ba198f24150f523e1242e83c4970de4a525480586be5dcc24d9add32c5 | 3,407,975 | 32 | 7 | 10,384,409 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-linux_armv6l.whl | 7cfe36b56e8489dee8fbc777c61959f60ec0f1f11817e8f2415f429552846aed | 10,467,650 | 7 | 4 | 22,696,387 | scanned |
| pluggy 1.6.0 | sdist | pluggy-1.6.0.tar.gz | 7dcc130b76258d33b90f61b658791dede3486c3e6bfb003ee5c9bfb396dd22f3 | 69,412 | 87 | 9 | 399,360 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp312-cp312-macosx_10_13_x86_64.whl | 7f047e29dcae44602496db43be01ad42fc6f1cc0d8cd6c83d342306c32270196 | 182,063 | 28 | 6 | 591,681 | scanned |
| tokenizers 0.23.2 | sdist | tokenizers-0.23.2.tar.gz | 7f0f085686b9de0d0079e6f874ae053600db64c5d13049e0bbc0119926d25aac | 385,745 | 187 | 12 | 2,092,544 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp311-cp311-win32.whl | 8098f252adfa6c80ab48096053f512f2321f0b998f98150cea9bd23d83e1467b | 142,543 | 24 | 5 | 448,052 | scanned |
| hf-xet 1.7.0 | wheel | hf_xet-1.7.0-cp38-abi3-musllinux_1_2_aarch64.whl | 80f79dae613ce9e0ea1fd1ae15616ca9ac74aed4c770aabc199c4f03ebecc863 | 4,190,628 | 8 | 6 | 12,104,107 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp311-cp311-macosx_14_0_x86_64.whl | 8155154c7c691289fe18f510b5d4657c68c67989f293f0535a91360392ff6538 | 6,798,936 | 1,162 | 77 | 24,065,305 | scanned |
| ctranslate2 4.8.2 | wheel | ctranslate2-4.8.2-cp311-cp311-macosx_11_0_x86_64.whl | 8221875b09ef982e3579a5165f8c9fcfb3d5de0f710af228eca2f73d69635ace | 11,929,414 | 38 | 9 | 61,452,235 | scanned |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-macosx_10_13_x86_64.whl | 84c540759e8e7f01e690e197e04060f48899d37cea322299f255843273d3385d | 44,278,407 | 224 | 15 | 141,349,056 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp311-cp311-manylinux2014_s390x.manylinux_2_17_s390x.manylinux_2_28_s390x.whl | 850774a7879607d3a6f50d36d04f00ee69e7fc816450e5f7e58d7f17f1ae5c00 | 882,114 | 28 | 6 | 3,127,196 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-macosx_10_12_x86_64.whl | 85a9a357a3764aecc904ee76bdaf8cf1ad8e5a67a1b929a487c4a39b49ed0e90 | 3,148,852 | 32 | 7 | 10,090,588 | scanned |
| av 15.1.0 | wheel | av-15.1.0-cp312-cp312-manylinux_2_28_aarch64.whl | 86226d2474c80c3393fa07a9c366106029ae500716098b72b3ec3f67205524c3 | 38,319,710 | 273 | 97 | 112,219,048 | scanned |
| pytest 8.4.2 | sdist | pytest-8.4.2.tar.gz | 86c0d0b93306b961d58d62a4db4879f27fe25513d4b969df351abdddb3c30e01 | 1,519,618 | 698 | 8 | 7,444,480 | scanned |
| pytest 8.4.2 | wheel | pytest-8.4.2-py3-none-any.whl | 872f880de3fc3a5bdc88a11b39c9710c3497a547cfa9320bc3c5e62fbf272e79 | 365,750 | 81 | 6 | 1,288,708 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp311-cp311-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl | 89cd468399cfd2504718f0ba50e410dca55a170b61a02ad92bb18c8a65186e93 | 16,918,164 | 1,166 | 80 | 57,360,224 | scanned |
| protobuf 7.36.2 | wheel | protobuf-7.36.2-cp310-abi3-manylinux2014_x86_64.whl | 89f23aa53c24553a2416fd4fd1ec06f74fa42b14b546d8883128813f775bbfd2 | 343,223 | 63 | 5 | 1,388,238 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-pp311-pypy311_pp73-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl | 8ad03c0965fb3c692200e74d458ca28c1dbb4ce96f9a479a8aa041ad5fabca02 | 16,747,286 | 1,166 | 80 | 56,948,453 | scanned |
| trove-classifiers 2026.9.21.13 | wheel | trove_classifiers-2026.9.21.13-py3-none-any.whl | 8b1ff4f9c191b1040b71c37f1e445ab99732911e3cd91de52838453a854d7a17 | 14,232 | 9 | 5 | 58,517 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp312-cp312-musllinux_1_2_aarch64.whl | 8dc52c23056b9ddd46818a57b78404882310fb473d63f17b07d5c40421e47f8e | 761,089 | 28 | 6 | 2,109,677 | scanned |
| fsspec 2026.9.0 | wheel | fsspec-2026.9.0-py3-none-any.whl | 8dd6e646e99ea382bd85f97a45e6b526a442d79423a7dc673f1e2756d05fcb5f | 221,738 | 62 | 4 | 810,582 | scanned |
| greenlet 3.5.6 | sdist | greenlet-3.5.6.tar.gz | 8e67c43bdfc88d5fee6db0d3e40175b362fc95fb85f0412d233b9b203c53a575 | 207,653 | 143 | 9 | 1,003,520 | scanned |
| av 15.1.0 | wheel | av-15.1.0-cp312-cp312-musllinux_1_2_x86_64.whl | 8f383949b010c3e731c245f80351d19dc0c08f345e194fc46becb1cb279be3ff | 41,150,592 | 278 | 102 | 115,142,719 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl | 90f9849678c75fe7afa2d348ac842c168b0a4d3d61919687216dfc547976d853 | 16,645,538 | 1,032 | 80 | 56,537,090 | scanned |
| iniconfig 2.3.1 | wheel | iniconfig-2.3.1-py3-none-any.whl | 9121e2c1fdb355232495be3194c8dfe87ccc2d5dee45947b78e68f499790d7a7 | 7,552 | 10 | 4 | 18,341 | scanned |
| protobuf 7.36.2 | wheel | protobuf-7.36.2-cp310-abi3-win32.whl | 912c1221170e16c08d1f086762f563dd61ff83c18b5fa6652952dfaded66f728 | 442,998 | 63 | 5 | 1,615,024 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl | 9149cad251584d5fb4981be1ecde53a1ca46c891a79788c0df828d2f166bda28 | 775,116 | 28 | 6 | 2,924,660 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-pp311-pypy311_pp73-macosx_14_0_x86_64.whl | 948424b06129ce883307e8cff868c31396d8dc7630a59c61d70d98dbe70f222c | 6,708,728 | 1,162 | 77 | 23,774,866 | scanned |
| packaging 26.3 | sdist | packaging-26.3.tar.gz | 94edc256424af38762eb31306eed28beb9f0efc50a8837492c9d6fd6004aed79 | 313,412 | 105 | 9 | 1,679,360 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-manylinux_2_17_s390x.manylinux2014_s390x.whl | 950d7c9426fa72406a0ffeacdbc0bb9985f5db20eb8b263f29c79aaf83105703 | 3,591,899 | 32 | 7 | 11,576,291 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp312-cp312-win32.whl | 96b533f0e99f6579b3d4d4995707cf36df9100d67e0c8303a0c55b27b5f99bc5 | 137,658 | 24 | 5 | 449,588 | scanned |
| hatchling 1.27.0 | sdist | hatchling-1.27.0.tar.gz | 971c296d9819abb3811112fc52c7a9751c8d381898f36533bb16f9791e941fd6 | 54,983 | 79 | 6 | 358,400 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl | 975736b002ed080d124cf81a79cb7e05cb26d6b3f5c7a7b651c0fcce70353aa1 | 621,404 | 106 | 9 | 2,052,432 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-macosx_11_0_arm64.whl | 986670e43691469dcee610ea0f846f91a8f84e91fc6f7a48d4c064414c0ec2bf | 3,101,593 | 32 | 7 | 9,968,570 | scanned |
| ctranslate2 4.8.2 | wheel | ctranslate2-4.8.2-cp311-cp311-win_amd64.whl | 995938fcd24a1174a7abf9765e7fa216b5b91a1d8e8c4c8f383c7a186e8bab2e | 19,220,522 | 33 | 8 | 62,241,017 | scanned |
| av 15.1.0 | wheel | av-15.1.0-cp311-cp311-macosx_13_0_x86_64.whl | 9c7131494a3a318612b4ee4db98fe5bc50eb705f6b6536127c7ab776c524fd8b | 26,946,268 | 260 | 84 | 84,860,995 | scanned |
| anyio 4.15.1 | sdist | anyio-4.15.1.tar.gz | 9f28306018cbd6d329e64a36d58256edff76dd996fe423bc957326e578b82a94 | 276,966 | 144 | 7 | 1,587,200 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp311-cp311-win_amd64.whl | 9f3bfb4965eb874431221a3ff3fdcddc7e74e3b07799e0e84ca4a0f867d449bf | 158,763 | 24 | 5 | 482,877 | scanned |
| pathspec 1.1.1 | wheel | pathspec-1.1.1-py3-none-any.whl | a00ce642f577bf7f473932318056212bc4f8bfdf53128c78bbd5af0b9b20b189 | 57,328 | 36 | 4 | 164,568 | scanned |
| ctranslate2 4.8.2 | wheel | ctranslate2-4.8.2-cp311-cp311-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl | a24e0a95151b970941867fec94c983df978630f1996242a587c072d455607d28 | 39,378,274 | 38 | 10 | 139,168,690 | scanned |
| protobuf 7.36.2 | wheel | protobuf-7.36.2-cp310-abi3-win_amd64.whl | a300819d441e078a5608c0d3c709796bb548136058fda017ae51d425b44fd353 | 456,514 | 63 | 5 | 1,711,365 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl | a37039b5dfc4af84eb3ef0a92f4307e28936c8f9adccba2629d36f652e9bf7a2 | 3,516,830 | 32 | 7 | 11,462,687 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp312-cp312-macosx_11_0_universal2.whl | a5876d0a60355af98d535c47f6cd6eb0f8a432396dab26845d380b92f8412422 | 295,668 | 99 | 8 | 1,010,120 | scanned |
| av 15.1.0 | wheel | av-15.1.0-cp312-cp312-musllinux_1_2_aarch64.whl | a631ea879cc553080ee62874f4284765c42ba08ee0279851a98a85e2ceb3cc8d | 40,286,166 | 278 | 102 | 102,171,827 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp311-cp311-macosx_11_0_universal2.whl | a6a4b98a9132e0f45c9fc245a63894cfd8c45fb7a0d6bffc5eab3ec327cf7324 | 294,075 | 99 | 8 | 1,010,056 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp311-cp311-win_amd64.whl | a6b4ff33f7e011bbaa148238d131c4fd4f8afbab3c104ddfbdb2b12b74ff7016 | 323,317 | 99 | 8 | 857,839 | scanned |
| numpy 2.5.3 | wheel | numpy-2.5.3-cp312-cp312-macosx_14_0_arm64.whl | a72f874bc9e10e4b8f80426fb49716d5141f64442a0c8418065093ec8017fbb0 | 5,445,405 | 1,040 | 77 | 20,580,207 | scanned |
| idna 3.20 | sdist | idna-3.20.tar.gz | a7db850025b95ded1eae8a46181a1a6c56c92c96f0e2b005d9ff8dc0210cab44 | 216,463 | 31 | 3 | 2,007,040 | scanned |
| python-dateutil 2.9.0.post0 | wheel | python_dateutil-2.9.0.post0-py2.py3-none-any.whl | a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427 | 229,892 | 25 | 4 | 441,579 | scanned |
| idna 3.20 | wheel | idna-3.20-py3-none-any.whl | ab7ae7122974553370f0bdb919e1a960b2cd1bc1ef0276416d896db81c14582c | 69,583 | 16 | 5 | 342,091 | scanned |
| hf-xet 1.7.0 | wheel | hf_xet-1.7.0-cp38-abi3-win_arm64.whl | acc3851cf2576a8fb2ae926da863f4efabe21303cf292e9a44332802ab0dcc6a | 3,662,436 | 7 | 5 | 8,674,520 | scanned |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-manylinux1_x86_64.whl | ad21bc07516b187965a7521c5cf0df0bd657b17482eaad74335272d35a2b07de | 48,217,159 | 224 | 15 | 142,673,534 | scanned |
| pyee 13.0.1 | wheel | pyee-13.0.1-py3-none-any.whl | af2f8fede4171ef667dfded53f96e2ed0d6e6bd7ee3bb46437f77e3b57689228 | 15,659 | 14 | 4 | 39,755 | scanned |
| av 15.1.0 | wheel | av-15.1.0-cp312-cp312-macosx_13_0_x86_64.whl | af455ce65ada3d361f80c90c810d9bced4db5655ab9aa513024d6c71c5c476d5 | 26,953,097 | 260 | 84 | 85,003,845 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-win32.whl | b530c191970b143375b6a68e6f743800b2b786bbcf03a7965b06c4bf04568167 | 10,502,442 | 7 | 5 | 24,786,151 | scanned |
| numpy 2.5.3 | wheel | numpy-2.5.3-cp312-cp312-musllinux_1_2_x86_64.whl | b5d93cf48f687479941d12b69c873ad2cc76bbd487f0091c2200636497f34034 | 18,476,479 | 1,049 | 83 | 61,944,088 | scanned |
| av 15.1.0 | wheel | av-15.1.0-cp311-cp311-macosx_13_0_arm64.whl | b785948762a8d45fc58fc24a20251496829ace1817e9a7a508a348d6de2182c3 | 21,767,323 | 260 | 84 | 56,108,190 | scanned |
| numpy 2.5.3 | wheel | numpy-2.5.3-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl | b7e18c623bb5c95acb3b3328861272816ba199fb531921c5d6d0b675f1fde9e3 | 16,717,410 | 1,044 | 80 | 56,365,091 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl | b8bb0864c5a28024fac8a632c443c87c5aa6f215c0b126c449ae1a150412f31d | 806,638 | 28 | 6 | 2,874,560 | scanned |
| click 8.5.0 | sdist | click-8.5.0.tar.gz | ba0d2089de75ea0310e2dde03160e6ca10009947fb95a182f9b54021bb272e34 | 382,235 | 112 | 4 | 1,556,480 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl | ba1cc08a7ccde2d2ec775841541641e4548226580ab850948cbfda66a1befcdc | 807,870 | 28 | 6 | 2,903,648 | scanned |
| onnxruntime 1.30.0 | wheel | onnxruntime-1.30.0-cp311-cp311-manylinux_2_28_aarch64.whl | bac3aee7b40acd805659fd81a2acd6096312d5b0f014c97ddfe75fb4c1644627 | 21,332,697 | 353 | 15 | 55,701,456 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl | bb8481604b7a9e75eff53772496201690ce2687067e038b3cc31aaf16aa0b974 | 11,215,882 | 7 | 4 | 27,674,128 | scanned |
| protobuf 7.36.2 | wheel | protobuf-7.36.2-py3-none-any.whl | bdb3a345d48db958e6ce1f18e508beb0cc981d64f24088427549c866cd039f1e | 179,806 | 62 | 4 | 966,138 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-musllinux_1_2_i686.whl | bef235815a067b2648caf6dcc7a71091b0b0fff9ee8057f6451eb9335fae52ef | 10,146,224 | 34 | 9 | 27,714,893 | scanned |
| numpy 2.5.3 | wheel | numpy-2.5.3-cp312-cp312-win32.whl | bf63afbe037eb5d2fe87fbcc7778e61da53ebaf21d938a4515aa73b62532a5d4 | 6,133,378 | 942 | 68 | 21,306,402 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp312-cp312-musllinux_1_2_aarch64.whl | c1a2af6c6ef86344a6b0db6b97834208bf598db514f2b155042439b62605601a | 17,020,706 | 1,034 | 82 | 58,214,592 | scanned |
| tqdm 4.70.1 | wheel | tqdm-4.70.1-py3-none-any.whl | c293e525e6fef9c20e8728fd4612df02a0aa31bb5fe91ecd93e123b1b7bffa73 | 80,199 | 39 | 5 | 233,479 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp311-cp311-musllinux_1_2_aarch64.whl | c2d37ab77531417474168eb79d6d80b14f821a966818505d03013d0833edb7a8 | 17,322,877 | 1,168 | 82 | 59,160,424 | scanned |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-macosx_11_0_universal2.whl | c89fc4736502a1f0fac2c8ca5d10c0cbc1c669f1f4774a2d8507a43140e4d53f | 44,278,410 | 224 | 15 | 141,349,059 | scanned |
| av 15.1.0 | wheel | av-15.1.0-cp311-cp311-manylinux_2_28_x86_64.whl | c8ef597087db560514617143532b1fafc4825ebb2dda9a22418f548b113a0cc7 | 39,571,086 | 274 | 98 | 116,824,862 | scanned |
| numpy 2.5.3 | wheel | numpy-2.5.3-cp312-cp312-macosx_10_13_x86_64.whl | cb189f09db39283b26bfd061ec16189e14f71c6755207f72a0f7540867afe5b9 | 16,994,982 | 1,045 | 81 | 56,950,188 | scanned |
| ctranslate2 4.8.2 | wheel | ctranslate2-4.8.2-cp311-cp311-macosx_11_0_arm64.whl | cb2a5b4c206b3bd1f7f4b44d07e86e42050af6753053cdc86444f8d0ead9d6d8 | 1,271,641 | 37 | 8 | 4,952,362 | scanned |
| protobuf 7.36.2 | wheel | protobuf-7.36.2-cp310-abi3-macosx_10_9_universal2.whl | cbc70b17ee27e28894c7fee8bb04be1abead49e936bc70eb60052531eee2079e | 456,039 | 63 | 5 | 1,661,962 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-musllinux_1_2_i686.whl | cc8b22da8d9d6fdd844a68ae937e2a0adf9b16514e9a97cc60355e2d4b219fc3 | 10,733,525 | 7 | 4 | 23,753,002 | scanned |
| numpy 2.5.3 | wheel | numpy-2.5.3-cp312-cp312-win_arm64.whl | ccb32e0525d29e8b0572eb84c9a57af0e7a4e615726927506f55063c62414034 | 10,485,432 | 1,062 | 98 | 31,040,447 | scanned |
| tqdm 4.70.1 | sdist | tqdm-4.70.1.tar.gz | cefd0eca11b2a37a3aee776544d4f4ae913f02688135b5556b8788dfa474afc4 | 171,846 | 96 | 7 | 737,280 | scanned |
| filelock 4.0.12 | sdist | filelock-4.0.12.tar.gz | cf42711a7ac791818b299fab0332a088c65aeeefa36290de98db92c434303b0c | 253,880 | 88 | 3 | 1,280,000 | scanned |
| skills-ref 0.1.1 | wheel | skills_ref-0.1.1-py3-none-any.whl | d35db5bb8de71ae301daf5ca9cb71f8a555e8c6f83a6d40e46a5bc09f8f461b5 | 12,918 | 12 | 5 | 31,686 | scanned |
| hatchling 1.27.0 | wheel | hatchling-1.27.0-py3-none-any.whl | d3a2f3567c4f926ea39849cdf924c7e99e6686c9c8e288ae1037c8fa2a5d937b | 75,794 | 73 | 7 | 283,081 | scanned |
| av 15.1.0 | wheel | av-15.1.0-cp311-cp311-musllinux_1_2_x86_64.whl | d3f66ff200ea166e606cb3c5cb1bd2fc714effbec2e262a5d67ce60450c8234a | 40,878,695 | 278 | 102 | 113,989,078 | scanned |
| hf-xet 1.7.0 | sdist | hf_xet-1.7.0.tar.gz | d406ec79053c0871817f700c2ac8c36ba0d87f9c34b7458b0f0063bb218b0466 | 985,689 | 400 | 12 | 4,382,720 | scanned |
| av 15.1.0 | wheel | av-15.1.0-cp312-cp312-win_amd64.whl | d5921aa45f4c1f8c1a8d8185eb347e02aa4c3071278a2e2dd56368d54433d643 | 31,336,093 | 266 | 90 | 88,098,433 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-pp311-pypy311_pp73-macosx_11_0_arm64.whl | d6da64deb6b8ed903e7560180a92f2d804ee1ba5eeb849ac2748b8c1aba1f6d7 | 14,889,064 | 1,167 | 81 | 49,712,677 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp311-cp311-manylinux_2_39_riscv64.whl | d701eab36200c36224833d07dbdb709adb7fd4253429548ddb5e547b8ed40586 | 428,068 | 106 | 9 | 1,219,148 | scanned |
| packaging 26.3 | wheel | packaging-26.3-py3-none-any.whl | d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c | 129,956 | 29 | 8 | 499,179 | scanned |
| pyyaml 6.0.3 | sdist | pyyaml-6.0.3.tar.gz | d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f | 130,960 | 656 | 8 | 1,884,160 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp312-cp312-win_amd64.whl | d8e8286dd7cea7895157318d1b91cdacac64c479f3cbc8dce548331728484751 | 12,321,687 | 1,050 | 98 | 40,914,562 | scanned |
| httpx 0.28.1 | wheel | httpx-0.28.1-py3-none-any.whl | d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad | 73,517 | 29 | 5 | 295,303 | scanned |
| ctranslate2 4.8.2 | wheel | ctranslate2-4.8.2-cp312-cp312-win_amd64.whl | d94421d565d0de61c032998f737a18942b0f2bef40c0424b1846ec6f67300105 | 19,222,069 | 33 | 8 | 62,254,841 | scanned |
| onnxruntime 1.30.0 | wheel | onnxruntime-1.30.0-cp312-cp312-win_arm64.whl | dc4c706f1935ebb62356e6a095b047859badd854482c40560888e95c328ed262 | 14,175,072 | 323 | 13 | 42,377,407 | scanned |
| typing-extensions 4.16.0 | sdist | typing_extensions-4.16.0.tar.gz | dc983d19a509c94dba722ee6abd33940f7c05a89e243c47e907eb4db6f1a43e5 | 113,555 | 9 | 3 | 593,920 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp311-cp311-win32.whl | ddea102b48f9e339f3948bf22040944184627a30fdf7f858667673b9c5f033c8 | 6,233,945 | 1,058 | 68 | 21,214,669 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-win32.whl | debf978920d93ba9c219bd67cc4bbfaf912c9039e41e7a28b91ec15e3728c95a | 2,592,809 | 32 | 7 | 6,879,620 | scanned |
| numpy 2.5.3 | sdist | numpy-2.5.3.tar.gz | df2d5874ff183595a4ba404edd04f6bd9b5505c1d7708573f6a6c17489a67563 | 20,791,231 | 8,367 | 165 | 82,974,720 | scanned |
| protobuf 7.36.2 | wheel | protobuf-7.36.2-cp310-abi3-manylinux2014_aarch64.whl | e11e1f0180583a2af89db6a2ecd9e8dc40aa6d2988ca175bfd0e6d12ea72d74e | 344,219 | 63 | 5 | 1,413,063 | scanned |
| hf-xet 1.7.0 | wheel | hf_xet-1.7.0-cp38-abi3-macosx_10_12_x86_64.whl | e3e88a7a75d7d95cbee1f37dc31341d6201124cf21c6c4b1dfab8ccba9b09e0f | 3,796,096 | 7 | 5 | 8,275,673 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp312-cp312-win32.whl | e3eeb0aabd6bd5ce64faae67e9935203a6991b4bc2a485a767fbafb2c5125f45 | 5,962,825 | 930 | 68 | 20,497,614 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-win_arm64.whl | e49c394456dd9985787fec76132438ba3fb8911f857b1bf3d40119f9292d41aa | 2,729,352 | 32 | 7 | 7,473,032 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp312-cp312-musllinux_1_2_x86_64.whl | e5805d5a22fd19c8ccff10a9561f9df94436b0545619ea579db2d3c35294bce2 | 18,368,541 | 1,035 | 83 | 61,745,894 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-musllinux_1_2_armv7l.whl | e651e977a79e4c758eb807f0481d673a67ffe53cfa92209781dfa3a996cf8412 | 10,285,491 | 7 | 4 | 22,266,320 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-musllinux_1_2_aarch64.whl | e8058d2145566510790eab4e2fad186002e288dec5e0d343a92fe7b0bc1b3e13 | 10,543,416 | 7 | 4 | 23,395,349 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp312-cp312-manylinux_2_24_aarch64.manylinux_2_28_aarch64.whl | e85880b538e59a59f55117b81f208a6660ad5ac328aad9305f812d9b8bc67a0f | 611,700 | 106 | 9 | 2,488,031 | scanned |
| pluggy 1.6.0 | wheel | pluggy-1.6.0-py3-none-any.whl | e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746 | 20,538 | 14 | 4 | 65,823 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-musllinux_1_2_aarch64.whl | eb2f9c8a24da020ea8c11a01a19c1c2547912d92121ae4a01cfbca46125dee40 | 9,967,367 | 34 | 9 | 30,672,312 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp312-cp312-macosx_11_0_arm64.whl | ebfb099f8dcf083deef3ac1ca4c1503f387cf76296fcb3816b66f5ecb5f54fdb | 14,699,246 | 1,033 | 81 | 49,038,691 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp311-cp311-win_arm64.whl | ed9749eef4cbd126da3dc1d6bcb3a57f5eb7ac6a6484146bdbf743f552dfc577 | 10,479,528 | 1,184 | 98 | 30,770,579 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp312-cp312-manylinux_2_24_s390x.manylinux_2_28_s390x.whl | ee7d9da3bf493909cf811a3f038840cb34fab5ae2956b8a263919f6e289ab188 | 629,529 | 106 | 9 | 2,043,347 | scanned |
| greenlet 3.5.6 | wheel | greenlet-3.5.6-cp312-cp312-manylinux_2_24_ppc64le.manylinux_2_28_ppc64le.whl | f0ba7c2a329d650628f4c8572fd1db29f0a59dd70a3e3e0710dcf18a35cce9d8 | 624,223 | 106 | 9 | 2,563,731 | scanned |
| onnxruntime 1.30.0 | wheel | onnxruntime-1.30.0-cp312-cp312-win_amd64.whl | f3501472571f1b1eee50e017851e7929f5ea37312d2d8c2494a19e8fc58b4a38 | 14,311,470 | 323 | 13 | 41,864,423 | scanned |
| onnxruntime 1.30.0 | wheel | onnxruntime-1.30.0-cp311-cp311-macosx_14_0_arm64.whl | f36c87ec504f4f328e968ee322e4ba9682abe66280b3425625afcbed5333fed7 | 21,533,037 | 352 | 14 | 78,122,476 | scanned |
| numpy 2.4.6 | sdist | numpy-2.4.6.tar.gz | f3a3570c4a2a16746ac2c31a7c7c7b0c186b95ce902e33db6f28094ed7387dda | 20,735,807 | 8,250 | 146 | 82,350,080 | scanned |
| numpy 2.4.6 | wheel | numpy-2.4.6-cp311-cp311-musllinux_1_2_x86_64.whl | f407cb6b8e9d6d8c626bc73c945db1706035af8fd632295547bf1c9e46d092d6 | 18,651,487 | 1,169 | 83 | 62,569,096 | scanned |
| tokenizers 0.23.2 | wheel | tokenizers-0.23.2-cp310-abi3-musllinux_1_2_armv7l.whl | f486f402f6f9abee5bb032553736813af0c710a86b2e0ca592634c55cea1f835 | 9,811,886 | 34 | 9 | 29,989,368 | scanned |
| protobuf 7.36.2 | wheel | protobuf-7.36.2-cp310-abi3-manylinux2014_s390x.whl | f4fee11ec330d238b34a05c9b675f693c20415d1c5bd7d5320cc2f8a798eb9cf | 357,223 | 63 | 5 | 1,455,413 | scanned |
| numpy 2.5.3 | wheel | numpy-2.5.3-cp312-cp312-macosx_11_0_arm64.whl | f59a878c33d6b88122d80d239bb3b845d58708750b0cb06a09aebb9b18ec696c | 12,009,327 | 1,045 | 81 | 38,631,118 | scanned |
| ruff 0.14.14 | wheel | ruff-0.14.14-py3-none-manylinux_2_17_aarch64.manylinux2014_aarch64.whl | f666445819d31210b71e0a6d1c01e24447a20b85458eea25a25fe8142210ae0e | 10,585,753 | 7 | 4 | 24,014,498 | scanned |
| onnxruntime 1.30.0 | wheel | onnxruntime-1.30.0-cp312-cp312-manylinux_2_28_x86_64.whl | fa688e7891a6aa206636fe7372e27ee75fd17713289f6b4fc7b190e0a7de9328 | 23,585,654 | 353 | 15 | 63,773,725 | scanned |
| strictyaml 1.7.3 | wheel | strictyaml-1.7.3-py3-none-any.whl | fb5c8a4edb43bebb765959e420f9b3978d7f1af88c80606c03fb420888f5d1c7 | 123,917 | 46 | 4 | 601,413 | scanned |
| pyyaml 6.0.3 | wheel | pyyaml-6.0.3-cp312-cp312-macosx_11_0_arm64.whl | fc09d0aa354569bc501d4e787133afc08552722d3ab34836a80547331bb5d4a0 | 173,973 | 28 | 6 | 606,087 | scanned |
| numpy 2.5.3 | wheel | numpy-2.5.3-cp312-cp312-macosx_14_0_x86_64.whl | fc36dc566135b5eceec4cf89758fcb719266a019ef07dae1754ae7c9f617ef3e | 6,783,213 | 1,040 | 77 | 24,298,758 | scanned |
| hf-xet 1.7.0 | wheel | hf_xet-1.7.0-cp38-abi3-manylinux_2_28_aarch64.whl | fcfd6c22418e57dd5b3aea649e813b2e2cfb2aebf317b210d90f1fe4b3018b52 | 3,990,011 | 7 | 5 | 11,356,654 | scanned |
| playwright 1.63.0 | wheel | playwright-1.63.0-py3-none-macosx_11_0_arm64.whl | fd1aa00631d44d55e56e0975bf3f3f285fac4a9fd2813183f0c12a488f1a1b24 | 42,944,679 | 224 | 15 | 138,207,326 | scanned |
| onnxruntime 1.30.0 | wheel | onnxruntime-1.30.0-cp311-cp311-manylinux_2_28_x86_64.whl | fd54b314ea385bcecac69ab431f020ba503e3878dad4ebb645fec5a24b041242 | 23,561,046 | 353 | 15 | 63,716,381 | scanned |
| ctranslate2 4.8.2 | wheel | ctranslate2-4.8.2-cp312-cp312-macosx_11_0_arm64.whl | fedda669421a57f8164568ee86ea265727016988d310fcc2e24ca30e9ec457cd | 1,271,613 | 37 | 8 | 4,949,626 | scanned |
| six 1.17.0 | sdist | six-1.17.0.tar.gz | ff70335d468e7eb6ec65b95b99d3a2836546063f63acc5171de367e834932a81 | 34,031 | 19 | 7 | 174,080 | scanned |

## Candidate flag counts

| Flag | Rows |
|---|---:|
| dependency-metadata-name | 1,275 |
| license-notice-name | 2,254 |
| native-binary-extension | 2,571 |
| native-dependency-name | 369 |
