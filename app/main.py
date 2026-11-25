from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import campaigns, editor
from app.services.keitaro_client import KeitaroError
from app.services.stream_ops import OpError
from app.services.weights import WeightError
from app.services.sync import DirtyStreamError

app = FastAPI(title="Adrobot")
app.include_router(campaigns.router)
app.include_router(editor.router)


@app.exception_handler(OpError)
@app.exception_handler(WeightError)
async def bad_request(request: Request, exc: Exception):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(KeitaroError)
async def bad_gateway(request: Request, exc: KeitaroError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(DirtyStreamError)
async def conflict(request: Request, exc: DirtyStreamError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})

@app.get("/health")
def health():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")