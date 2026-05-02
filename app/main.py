import logging

from fastapi import FastAPI

from app.routers import answers, dementia, photos, questions


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)


app = FastAPI(version="1.0.0")

app.include_router(questions.router, prefix="/questions", tags=["Questions"])
app.include_router(answers.router, prefix="/answers", tags=["Answers"])
app.include_router(photos.router, prefix="/photos", tags=["Photos"])
app.include_router(dementia.router, prefix="/dementia", tags=["Dementia"])


@app.get("/", tags=["Health Check"])
def root():
    return {"status": "ok", "message": "Server is running!"}
