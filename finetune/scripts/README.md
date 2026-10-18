# scripts/ — launchers and compatibility entrypoints

Training/export launchers and workstation orchestration stay here. Canonical LLaMA-Factory data
implementations live in [`../llamafactory/`](../llamafactory/); see its README for the script catalog.

| script | what it does |
|---|---|
| `lf_train.sh <config>` | run a LLaMA-Factory config on `GPUS=<ids>` |
| `train_when_free.sh <config> [need_mib] [log]` | wait for a free card and retry a training launch after a detected OOM |
| `free_gpus.sh [need_mib] [gpu_list]` | list cards with the requested free memory |
| `lf_export.sh <config>` / `export_lora.sh <run_dir> [base]` | merge a LoRA adapter into `<run_dir>/merged` |
| `stop_dpo_pairs.sh` | build termination preference pairs (`TAG`, `BASE_MODEL` env), using the historical generator/output schema |
| `stop_dpo_round.sh <base_model> <tag>` | historical stop-DPO orchestration: pairs → train → merge |
| `supervisor2.sh` | process the workstation job queue in `queue.txt` |
| `sync_repo.sh` | legacy synchronization from the original workstation's external working tree; its scripts copy excludes Python files to preserve the compatibility forwarders |

These shell scripts retain workstation-specific paths and assumptions. The stop-DPO generation
interface and some queue entries refer to historical scripts; inspect and adapt them before use.
`sync_repo.sh` also predates the current directory ownership and should not be used to synchronize
this layout without updating it.

The following seven Python files are thin CLI forwarders, preserving existing command paths while
running the implementation in `../llamafactory/`:

- `audit_pairs.py`
- `build_pairs_3dcodebench.py`
- `convert_subdirs.py`
- `drop_old_pair_trees.py`
- `shrink_pair_images.py`
- `upload_pairs.py`
- `verify_unflattened_glsl.py`

Use `python llamafactory/<script>.py ...` from `finetune/` for new workflows. Historical per-experiment
drivers were archived outside this checkout; their absence is not filled by these compatibility paths.
