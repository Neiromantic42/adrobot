from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import campaigns

app = FastAPI(title="Adrobot")
app.include_router(campaigns.router)


@app.get("/health")
def health():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")