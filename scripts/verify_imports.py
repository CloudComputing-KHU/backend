"""모든 모듈 import 검증 스크립트"""
import sys

errors = []

modules = [
    ("app.main", "app"),
    ("app.routers.answers", "router"),
    ("app.routers.auth", "router"),
    ("app.routers.dementia", "router"),
    ("app.routers.devices", "router"),
    ("app.routers.notifications", "router"),
    ("app.routers.photos", "router"),
    ("app.routers.questions", "router"),
    ("app.schemas.answer", "AnswerRequest"),
    ("app.schemas.auth", "LoginRequest"),
    ("app.schemas.dementia", "DementiaAnalysisRequest"),
    ("app.schemas.device", "DeviceRegisterRequest"),
    ("app.schemas.notification", "NotificationItem"),
    ("app.schemas.photo", "PhotoResponse"),
    ("app.schemas.question", "Question"),
    ("app.services.auth_service", "auth_service"),
    ("app.services.dementia_service", "dementia_service"),
    ("app.services.notification_service", "notification_service"),
    ("app.services.photo_service", "photo_service"),
    ("app.services.question_service", "question_service"),
    ("app.services.storage_service", "storage_service"),
]

for mod_name, attr_name in modules:
    try:
        mod = __import__(mod_name, fromlist=[attr_name])
        obj = getattr(mod, attr_name)
        print(f"  OK  {mod_name}.{attr_name}")
    except Exception as e:
        print(f"  FAIL {mod_name}.{attr_name} -> {e}")
        errors.append((mod_name, str(e)))

print()
if errors:
    print(f"FAILED: {len(errors)} module(s) have import errors")
    for mod, err in errors:
        print(f"  - {mod}: {err}")
    sys.exit(1)
else:
    print(f"ALL {len(modules)} modules imported successfully")
