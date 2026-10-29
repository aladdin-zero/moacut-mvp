# MOACUT third-party notices

This distribution includes Python 3.12 and third-party Python libraries. Exact installed versions are recorded in build-info.json. The packages retain their upstream licenses. Copies of available license/notice files are in licenses/ and the runtime's *.dist-info directories. No application-source open-source license is granted by this notice.

- Python: https://www.python.org/ — Python Software Foundation license, see licenses/Python-LICENSE.txt.
- PyTorch and torchvision: https://pytorch.org/ — upstream package licenses and bundled third-party notices, including CUDA libraries where distributed by upstream. See licenses/torch, licenses/torchvision, runtime/Lib/site-packages/torch/lib and torch-*.dist-info.
- Transformers: https://github.com/huggingface/transformers — Apache-2.0.
- OWLv2 model: google/owlv2-base-patch16-ensemble, revision cfd3195ba4ea9592eec887ded089f4c08eff231d, https://huggingface.co/google/owlv2-base-patch16-ensemble — Apache-2.0 as declared by its official model card. See models/owlv2/README.md, download-manifest.json and licenses/OWLv2-Apache-2.0.txt. Model weights are included for offline inference, not downloaded at runtime.
- OpenCV, NumPy, SciPy, Pillow and other dependencies: see their package metadata and licenses/ subdirectories.
- Windows .NET Framework, Windows speech and the default browser are system components and are not included in this ZIP. Windows license terms remain applicable.

Build-only static libraries, headers, debug symbols, developer caches, user photographs, API credentials and test fixtures are excluded from the client runtime bundle.
