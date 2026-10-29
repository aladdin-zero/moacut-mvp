# MOACUT MVP
Windows local camera application. Runtime source is camera-test/, Windows launcher/build tools are packaging/.
Preserve user photos and metadata. No paid API or remote image transmission. Model inference runs offline from models/owlv2.
Keep dependency versions pinned. Do not commit credentials, photographs, generated runtime or model weights.
Validate with python -m unittest discover -s camera-test -p "test_*.py" -v, node --test camera-test/test_capture_flow.cjs and node --check camera-test/web/app.js.
Build with packaging/build_release.py using a fresh output directory. ZIP binaries belong in GitHub Releases, not Git history.
