"""Host the Imprint API on Modal.

    modal secret create imprint-relayer IMPRINT_RELAYER_KEY=0x...   (once; testnet-only wallet)
    modal deploy deploy/modal_app.py

The image is built once (CPU PyTorch, TrustMark weights baked in) and the FastAPI app is served
as an ASGI app. The container stays warm for a while after each request and scales to zero otherwise.
"""
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent.parent
SERVICE = ROOT / "service"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libglib2.0-0", "libgl1")
    .pip_install("torch", "torchvision", index_url="https://download.pytorch.org/whl/cpu")
    .pip_install_from_requirements(str(ROOT / "deploy" / "space" / "requirements.txt"))
    .run_commands(
        "python -c \"from trustmark import TrustMark; TrustMark(verbose=False, model_type='Q', "
        "encoding_type=TrustMark.Encoding.BCH_5); print('model ready')\""
    )
    .add_local_dir(str(SERVICE), remote_path="/app/service", ignore=["__pycache__", "*.pyc", ".pytest_cache"])
)

app = modal.App("imprint-api", image=image)

# Runs in the container's global scope, which is what the memory snapshot captures. Importing torch and
# loading the watermark model here means a cold container restores with the model already in memory.
with image.imports():
    import os as _os
    import sys as _sys

    if _os.path.isdir("/app/service"):  # only inside the container; this block also runs locally at deploy time
        _sys.path.insert(0, "/app/service")
        _os.chdir("/app/service")
        import core as _core

        _core.payload_bits()


@app.function(
    secrets=[modal.Secret.from_name("imprint-relayer")],
    cpu=2.0,
    memory=3072,
    timeout=300,
    scaledown_window=600,
    min_containers=0,
    enable_memory_snapshot=True,  # model and imports are restored from a snapshot, so cold starts are short
)
@modal.concurrent(max_inputs=2)  # matches IMPRINT_MAX_BUSY; the watermark model is serialized anyway
@modal.asgi_app()
def api():
    from app import app as fastapi_app  # core and the model are already loaded (see above)

    return fastapi_app
