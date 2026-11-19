from fastapi import FastAPI

app = FastAPI(title="Adrobot")

@app.get("/health")
def health():
    return {"status": "ok"}