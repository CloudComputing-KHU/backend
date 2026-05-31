import os
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key

from app.services.family_service import normalize_role
from app.services.dynamodb_service import dynamodb_service, _build_update_expr, _strip_none


class UserProfileService:
    @property
    def _table_name(self) -> str:
        return os.getenv("DYNAMODB_USER_PROFILES_TABLE", "user_profiles")

    def is_configured(self) -> bool:
        return dynamodb_service.is_configured()

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

        updates: dict = _strip_none({
            "email": email,
            "name": name,
            "role": normalize_role(role),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        if is_confirmed is not None:
            updates["is_confirmed"] = is_confirmed
        if last_login_at is not None:
            updates["last_login_at"] = last_login_at.isoformat()

        expr, names, values = _build_update_expr(updates)
        dynamodb_service.table(self._table_name).update_item(
            Key={"user_id": user_id},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )

    def mark_confirmed_by_email(self, email: str) -> None:
        if not self.is_configured() or not email:
            return

        table = dynamodb_service.table(self._table_name)
        resp = table.query(
            IndexName="email-index",
            KeyConditionExpression=Key("email").eq(email),
            Limit=1,
        )
        items = resp.get("Items", [])
        if not items:
            return

        table.update_item(
            Key={"user_id": items[0]["user_id"]},
            UpdateExpression="SET #ic = :ic, #ua = :ua",
            ExpressionAttributeNames={"#ic": "is_confirmed", "#ua": "updated_at"},
            ExpressionAttributeValues={
                ":ic": True,
                ":ua": datetime.now(timezone.utc).isoformat(),
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
