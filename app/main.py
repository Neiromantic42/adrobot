from fastapi import FastAPI

from app.api import campaigns

app = FastAPI(title="Adrobot")
app.include_router(campaigns.router)


@app.get("/health")
def health():
    return {"status": "ok"}