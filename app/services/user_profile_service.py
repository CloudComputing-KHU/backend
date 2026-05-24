import os
from datetime import datetime, timezone

from app.services.family_service import normalize_role
from app.services.supabase_service import supabase_service


class UserProfileService:
    @property
    def _table(self) -> str:
        return os.getenv("SUPABASE_USER_PROFILES_TABLE", "user_profiles")

    def is_configured(self) -> bool:
        return supabase_service.is_configured()

    def upsert_profile(
        self,
        *,
        user_id: str,
        email: str | None,
        name: str | None,
        role: str | None,
        is_confirmed: bool | None = None,
        last_login_at: datetime | None = None,
    ) -> None:
        if not self.is_configured() or not user_id:
            return
        payload = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "role": normalize_role(role),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if is_confirmed is not None:
            payload["is_confirmed"] = is_confirmed
        if last_login_at is not None:
            payload["last_login_at"] = last_login_at.isoformat()
        supabase_service.upsert(self._table, payload, on_conflict="user_id")

    def mark_confirmed_by_email(self, email: str) -> None:
        if not self.is_configured() or not email:
            return
        supabase_service.update(
            self._table,
            filters=[("email", f"eq.{email}")],
            payload={
                "is_confirmed": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def sync_from_claims(self, claims: dict) -> None:
        user_id = claims.get("sub")
        if not user_id:
            return
        self.upsert_profile(
            user_id=user_id,
            email=claims.get("email"),
            name=claims.get("name"),
            role=claims.get("custom:role") or claims.get("role") or claims.get("app_role"),
            is_confirmed=bool(claims.get("email_verified", True)),
            last_login_at=datetime.now(timezone.utc),
        )


user_profile_service = UserProfileService()
