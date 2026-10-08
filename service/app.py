"""HTTP face of the image service. Run:  uvicorn app:app --port 8000"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

import core

MAX_BYTES = 12 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    core.payload_bits()  # load the model once at startup, not on the first request
    yield


app = FastAPI(title="Imprint image service", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file is larger than 12 MB")
    return data


@app.get("/health")
def health():
    return {"ok": True, "payload_bits": core.payload_bits()}


@app.post("/mark")
async def mark(file: UploadFile = File(...)):
    data = await _read_upload(file)
    try:
        return core.mark(data)
    except core.BadImage as e:
        raise HTTPException(400, str(e))


@app.post("/check")
async def check(file: UploadFile = File(...)):
    data = await _read_upload(file)
    try:
        return core.read(data)
    except core.BadImage as e:
        raise HTTPException(400, str(e))
