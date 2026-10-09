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


@app.function(
    secrets=[modal.Secret.from_name("imprint-relayer")],
    cpu=2.0,
    memory=3072,
    timeout=300,
    scaledown_window=600,
    min_containers=0,
)
@modal.concurrent(max_inputs=4)
@modal.asgi_app()
def api():
    import sys

    sys.path.insert(0, "/app/service")
    import os

    os.chdir("/app/service")
    from app import app as fastapi_app

    return fastapi_app
