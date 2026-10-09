# Model provenance

The setup command pins each Faster Whisper repository to a full Hugging Face
commit ID. It does not resolve the mutable `main` branch. The values below are
also defined in `douyin_transcript.models.ModelSpec` and passed as
`revision=` to `huggingface_hub.snapshot_download`.

| Profile | Repository | Pinned revision |
| --- | --- | --- |
| `balanced` | `Systran/faster-whisper-medium` | `08e178d48790749d25932bbc082711ddcfdfbc4f` |
| `fast` | `Systran/faster-whisper-small` | `536b0662742c02347bc0e980a01041f333bce120` |

## Source and selection record

On 2026-10-08, the Hugging Face Hub model API reported these commit IDs as the
current revisions of the repositories. The official repository trees at those
commit IDs list `model.bin`, `config.json`, and `tokenizer.json`, the files
required by this project's local completeness check:

- [Medium repository at the pinned commit](https://huggingface.co/Systran/faster-whisper-medium/tree/08e178d48790749d25932bbc082711ddcfdfbc4f)
- [Small repository at the pinned commit](https://huggingface.co/Systran/faster-whisper-small/tree/536b0662742c02347bc0e980a01041f333bce120)

The [medium revision API response](https://huggingface.co/api/models/Systran/faster-whisper-medium/revision/08e178d48790749d25932bbc082711ddcfdfbc4f)
and [small revision API response](https://huggingface.co/api/models/Systran/faster-whisper-small/revision/536b0662742c02347bc0e980a01041f333bce120)
were also queried directly to confirm each full `sha` and the expected file
names at that exact revision. Revisions identify immutable repository snapshots;
changing a revision is a model supply chain update and should be reviewed with
transcription-quality and performance regression evidence.

This pinning change was verified with mocked setup tests. The model weights were
not downloaded, file digests were not independently recomputed, and real model
loading or transcription was not tested as part of the pinning change.
