from fastapi import FastAPI
from app.routers import questions, answers, photos

app = FastAPI(
    version="1.0.0"
)

app.include_router(questions.router, prefix="/questions", tags=["Questions"])
app.include_router(answers.router, prefix="/answers", tags=["Answers"])
app.include_router(photos.router, prefix="/photos", tags=["Photos"])

@app.get("/", tags=["Health Check"])
def root():
    return {"status": "ok", "message": "Server is running!"}
