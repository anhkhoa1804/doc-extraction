# 042 execution environment

The VM is CPU-only for this experiment.

| item | value |
| --- | --- |
| Python | 3.12.14 (`.venvs/doc-extraction-linux312`) |
| torch | 2.14.0+cpu |
| CUDA | unavailable (`torch.cuda.is_available() == False`) |
| torchvision | 0.29.0+cpu |
| Docling | installed in the venv |
| EasyOCR | 1.7.2; import requires `libGL.so.1` |
| device | `cpu` via `configs/cpu.yaml` |

The baseline sample initially failed at layout import because the VM did not
expose `libGL.so.1`, even though EasyOCR and cv2 were installed. The rerun
used the pre-existing local `libglvnd0`, `libglx0`, and `libgl1` Debian package
files extracted into a temporary `/tmp` directory and exposed with
`LD_LIBRARY_PATH`. No package was installed system-wide and the `.deb` files
are not experiment artifacts. The TableTransformer weights were already in
the local Hugging Face cache; `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1` prevented network access during inference.

This workaround is provenance, not a scientific treatment or a production
semantic change. The initial 40-page replay completed with zero operational
failures under it.
