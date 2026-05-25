import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import answers, auth, dementia, devices, family, notifications, photos, questions
from app.services.photo_service import photo_service
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduled_photos = photo_service.get_scheduled_photos()
    now = datetime.now(timezone.utc)
    for photo in scheduled_photos:
        scheduled_at = photo.get("scheduled_at")
        if isinstance(scheduled_at, str):
            scheduled_at = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        if scheduled_at and scheduled_at.replace(tzinfo=scheduled_at.tzinfo or timezone.utc) <= now:
            updated = photo_service._backend().mark_photo_sent(photo["photo_id"])
            if updated:
                notification_service.send(
                    user_id=updated["receiver_user_id"],
                    title="새 사진이 도착했어요",
                    body=updated.get("caption") or "가족이 사진을 보냈어요.",
                    data={"photo_id": updated["photo_id"], "type": "photo_received"},
                )
                logger.info("재시작 후 지연 사진 즉시 발송 - photo_id=%s", photo["photo_id"])
        else:
            asyncio.create_task(photo_service.schedule_dispatch(photo))
            logger.info("재시작 후 예약 사진 task 재생성 - photo_id=%s", photo["photo_id"])
    yield


app = FastAPI(version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(family.router, prefix="/family", tags=["Family"])
app.include_router(questions.router, prefix="/questions", tags=["Questions"])
app.include_router(answers.router, prefix="/answers", tags=["Answers"])
app.include_router(photos.router, prefix="/photos", tags=["Photos"])
app.include_router(dementia.router, prefix="/dementia", tags=["Dementia"])
app.include_router(devices.router, prefix="/devices", tags=["Devices"])
app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])


@app.get("/", tags=["Health Check"])
def root():
    return {"status": "ok", "message": "Server is running!"}
