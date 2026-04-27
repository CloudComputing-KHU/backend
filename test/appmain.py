from fastapi import FastAPI

app = FastAPI(
    version="1.0.0"
)

@app.get("/", tags=["Health Check"])
def root():
    return {"status": "ok", "message": "Server is running!"}

@app.get("/health", tags=["Health Check"])
def health():
    return {"status": "ok"}
