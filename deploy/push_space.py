"""Create or update the Hugging Face Docker Space that hosts the Imprint API.

Needs: HF_TOKEN (write token) in the environment, and the relayer key either in
IMPRINT_RELAYER_KEY or at ~/.imprint/deployer.json. The key is set as a Space secret, never
written into the uploaded files.

usage: python deploy/push_space.py <hf-username>/<space-name>
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

repo_id = sys.argv[1] if len(sys.argv) > 1 else sys.exit("usage: push_space.py <user>/<space>")
token = os.environ.get("HF_TOKEN") or sys.exit("HF_TOKEN is not set")
here = Path(__file__).resolve().parent.parent

key = os.environ.get("IMPRINT_RELAYER_KEY")
if not key:
    data = json.loads((Path.home() / ".imprint" / "deployer.json").read_text())
    key = data["data"][0]["private_key"] if "data" in data else data["private_key"]

api = HfApi(token=token)
api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
api.add_space_secret(repo_id, "IMPRINT_RELAYER_KEY", key)
api.add_space_variable(repo_id, "IMPRINT_PER_IP_HOUR", os.environ.get("IMPRINT_PER_IP_HOUR", "12"))
api.add_space_variable(repo_id, "IMPRINT_GLOBAL_DAY", os.environ.get("IMPRINT_GLOBAL_DAY", "150"))

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "space"
    subprocess.run([str(here / "deploy" / "build_space.sh"), str(out)], check=True)
    api.upload_folder(repo_id=repo_id, repo_type="space", folder_path=str(out),
                      commit_message="Imprint API", delete_patterns=["*"])
print(f"pushed. Space: https://huggingface.co/spaces/{repo_id}")
print(f"API base URL once built: https://{repo_id.replace('/', '-').replace('_', '-').lower()}.hf.space")
