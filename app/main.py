import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import answers, auth, dementia, devices, photos, questions


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)


app = FastAPI(version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(questions.router, prefix="/questions", tags=["Questions"])
app.include_router(answers.router, prefix="/answers", tags=["Answers"])
app.include_router(photos.router, prefix="/photos", tags=["Photos"])
app.include_router(dementia.router, prefix="/dementia", tags=["Dementia"])
app.include_router(devices.router, prefix="/devices", tags=["Devices"])


@app.get("/", tags=["Health Check"])
def root():
    return {"status": "ok", "message": "Server is running!"}
