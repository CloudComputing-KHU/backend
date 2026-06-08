import os
import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from boto3.dynamodb.conditions import Attr, Key

from app.services.dynamodb_service import dynamodb_service, _convert_decimals

INVITE_TTL_MINUTES = 10
INVITE_CODE_LENGTH = 4
MAX_CODE_GENERATION_ATTEMPTS = 100

mock_family_invites: list[dict] = []
mock_family_links: list[dict] = []


def normalize_role(raw_role: str | None) -> str | None:
    if not raw_role:
        return None
    role = raw_role.lower()
    if role in {"child", "children"}:
        return "child"
    if role in {"parent", "guardian"}:
        return "parent"
    return None


def get_role_from_claims(current_user: dict) -> str | None:
    return normalize_role(
        current_user.get("custom:role")
        or current_user.get("role")
        or current_user.get("app_role")
    )


def require_role(current_user: dict, expected_role: str) -> None:
    if get_role_from_claims(current_user) != expected_role:
        raise HTTPException(
            status_code=403,
            detail=f"{expected_role} 역할 사용자만 사용할 수 있습니다.",
        )


class InMemoryFamilyBackend:
    @staticmethod
    def _expire_stale_invites() -> None:
        now = datetime.now()
        for invite in mock_family_invites:
            if invite["status"] == "pending" and invite["expires_at"] < now:
                invite["status"] = "expired"

    @staticmethod
    def get_active_link_for_user(user_id: str) -> dict | None:
        for link in mock_family_links:
            if link["status"] != "active":
                continue
            if link["parent_user_id"] == user_id or link["child_user_id"] == user_id:
                return link
        return None

    @staticmethod
    def _get_pending_invite_for_child(child_user_id: str) -> dict | None:
        pending_invites = [
            invite
            for invite in mock_family_invites
            if invite["child_user_id"] == child_user_id and invite["status"] == "pending"
        ]
        if not pending_invites:
            return None
        return max(pending_invites, key=lambda invite: invite["created_at"])

    @staticmethod
    def _find_pending_invite_by_code(invite_code: str) -> dict | None:
        for invite in mock_family_invites:
            if invite["invite_code"] == invite_code and invite["status"] == "pending":
                return invite
        return None

    @staticmethod
    def _generate_invite_code() -> str:
        active_codes = {
            invite["invite_code"]
            for invite in mock_family_invites
            if invite["status"] == "pending"
        }
        for _ in range(MAX_CODE_GENERATION_ATTEMPTS):
            invite_code = f"{random.randint(0, 9999):0{INVITE_CODE_LENGTH}d}"
            if invite_code not in active_codes:
                return invite_code
        raise HTTPException(status_code=500, detail="초대 코드 생성에 실패했습니다.")

    def create_invite(self, child_user_id: str) -> dict:
        self._expire_stale_invites()

        if self.get_active_link_for_user(child_user_id):
            raise HTTPException(
                status_code=409,
                detail="이미 연결된 가족이 있어 새 초대 코드를 생성할 수 없습니다.",
            )

        existing_invite = self._get_pending_invite_for_child(child_user_id)
        if existing_invite:
            return existing_invite

        created_at = datetime.now()
        invite_record = {
            "invite_id": f"invite_{uuid.uuid4().hex[:8]}",
            "invite_code": self._generate_invite_code(),
            "child_user_id": child_user_id,
            "status": "pending",
            "created_at": created_at,
            "expires_at": created_at + timedelta(minutes=INVITE_TTL_MINUTES),
            "used_at": None,
        }
        mock_family_invites.append(invite_record)
        return invite_record

    def connect_parent(self, parent_user_id: str, invite_code: str) -> dict:
        self._expire_stale_invites()

        if self.get_active_link_for_user(parent_user_id):
            raise HTTPException(
                status_code=409,
                detail="이미 연결된 가족이 있어 새 연결을 생성할 수 없습니다.",
            )

        invite_record = self._find_pending_invite_by_code(invite_code)
        if not invite_record:
            latest_same_code = next(
                (
                    invite
                    for invite in reversed(mock_family_invites)
                    if invite["invite_code"] == invite_code
                ),
                None,
            )
            if latest_same_code and latest_same_code["status"] == "expired":
                raise HTTPException(status_code=400, detail="만료된 초대 코드입니다.")
            if latest_same_code and latest_same_code["status"] == "used":
                raise HTTPException(status_code=409, detail="이미 사용된 초대 코드입니다.")
            raise HTTPException(status_code=404, detail="유효한 초대 코드를 찾을 수 없습니다.")

        child_user_id = invite_record["child_user_id"]
        if child_user_id == parent_user_id:
            raise HTTPException(status_code=400, detail="본인 계정끼리는 연결할 수 없습니다.")

        if self.get_active_link_for_user(child_user_id):
            raise HTTPException(status_code=409, detail="이미 사용된 초대 코드입니다.")

        connected_at = datetime.now()
        link_record = {
            "link_id": f"link_{uuid.uuid4().hex[:8]}",
            "parent_user_id": parent_user_id,
            "child_user_id": child_user_id,
            "status": "active",
            "created_at": connected_at,
            "connected_at": connected_at,
        }
        mock_family_links.append(link_record)
        invite_record["status"] = "used"
        invite_record["used_at"] = connected_at
        return link_record

    def get_my_family(self, user_id: str, role: str | None) -> dict:
        self._expire_stale_invites()

        active_link = self.get_active_link_for_user(user_id)
        pending_invite = None
        if role == "child":
            pending_invite = self._get_pending_invite_for_child(user_id)

        return {
            "user_id": user_id,
            "role": role,
            "active_link": active_link,
            "pending_invite": pending_invite,
        }


class DynamoDBFamilyBackend:
    @staticmethod
    def is_configured() -> bool:
        return dynamodb_service.is_configured()

    @property
    def invites_table(self) -> str:
        return os.getenv("DYNAMODB_FAMILY_INVITES_TABLE", "family_invites")

    @property
    def links_table(self) -> str:
        return os.getenv("DYNAMODB_FAMILY_LINKS_TABLE", "family_links")

    def _expire_stale_invites_for_child(self, child_user_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        table = dynamodb_service.table(self.invites_table)
        resp = table.query(
            KeyConditionExpression=Key("child_user_id").eq(child_user_id),
            FilterExpression=Attr("status").eq("pending") & Attr("expires_at").lt(now),
        )
        for item in resp.get("Items", []):
            table.update_item(
                Key={"child_user_id": child_user_id, "created_at": item["created_at"]},
                UpdateExpression="SET #s = :s",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":s": "expired"},
            )

    def get_active_link_for_user(self, user_id: str) -> dict | None:
        table = dynamodb_service.table(self.links_table)

        resp = table.query(
            IndexName="parent-index",
            KeyConditionExpression=Key("parent_user_id").eq(user_id) & Key("status").eq("active"),
            Limit=1,
        )
        items = resp.get("Items", [])
        if items:
            return _convert_decimals(items[0])

        resp = table.query(
            IndexName="child-index",
            KeyConditionExpression=Key("child_user_id").eq(user_id) & Key("status").eq("active"),
            Limit=1,
        )
        items = resp.get("Items", [])
        return _convert_decimals(items[0]) if items else None

    def _get_pending_invite_for_child(self, child_user_id: str) -> dict | None:
        self._expire_stale_invites_for_child(child_user_id)
        now = datetime.now(timezone.utc).isoformat()
        table = dynamodb_service.table(self.invites_table)
        # Limit 없이 전체 조회 후 앱에서 첫 번째 선택 (DynamoDB Limit은 FilterExpression 전에 적용됨)
        resp = table.query(
            KeyConditionExpression=Key("child_user_id").eq(child_user_id),
            FilterExpression=Attr("status").eq("pending") & Attr("expires_at").gt(now),
            ScanIndexForward=False,
            ConsistentRead=True,
        )
        items = resp.get("Items", [])
        return _convert_decimals(items[0]) if items else None

    def _find_pending_invite_by_code(self, invite_code: str) -> dict | None:
        now = datetime.now(timezone.utc).isoformat()
        table = dynamodb_service.table(self.invites_table)
        resp = table.query(
            IndexName="invite-code-index",
            KeyConditionExpression=Key("invite_code").eq(invite_code) & Key("status").eq("pending"),
        )
        for item in sorted(resp.get("Items", []), key=lambda x: x.get("created_at", ""), reverse=True):
            if item.get("expires_at", "") < now:
                table.update_item(
                    Key={"child_user_id": item["child_user_id"], "created_at": item["created_at"]},
                    UpdateExpression="SET #s = :s",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":s": "expired"},
                )
            else:
                return _convert_decimals(item)
        return None

    def _find_latest_invite_by_code(self, invite_code: str) -> dict | None:
        now = datetime.now(timezone.utc).isoformat()
        table = dynamodb_service.table(self.invites_table)
        resp = table.query(
            IndexName="invite-code-index",
            KeyConditionExpression=Key("invite_code").eq(invite_code),
        )
        items = resp.get("Items", [])
        if not items:
            return None
        item = max(items, key=lambda x: x.get("created_at", ""))
        item = dict(item)
        if item.get("status") == "pending" and item.get("expires_at", "") < now:
            item["status"] = "expired"
        return _convert_decimals(item)

    def _generate_invite_code(self) -> str:
        table = dynamodb_service.table(self.invites_table)
        for _ in range(MAX_CODE_GENERATION_ATTEMPTS):
            invite_code = f"{random.randint(0, 9999):0{INVITE_CODE_LENGTH}d}"
            resp = table.query(
                IndexName="invite-code-index",
                KeyConditionExpression=Key("invite_code").eq(invite_code) & Key("status").eq("pending"),
                Limit=1,
            )
            if not resp.get("Items"):
                return invite_code
        raise HTTPException(status_code=500, detail="초대 코드 생성에 실패했습니다.")

    def create_invite(self, child_user_id: str) -> dict:
        self._expire_stale_invites_for_child(child_user_id)

        if self.get_active_link_for_user(child_user_id):
            raise HTTPException(
                status_code=409,
                detail="이미 연결된 가족이 있어 새 초대 코드를 생성할 수 없습니다.",
            )

        existing_invite = self._get_pending_invite_for_child(child_user_id)
        if existing_invite:
            return existing_invite

        created_at = datetime.now(timezone.utc)
        invite_record = {
            "invite_id": f"invite_{uuid.uuid4().hex[:8]}",
            "invite_code": self._generate_invite_code(),
            "child_user_id": child_user_id,
            "status": "pending",
            "created_at": created_at.isoformat(),
            "expires_at": (created_at + timedelta(minutes=INVITE_TTL_MINUTES)).isoformat(),
        }
        dynamodb_service.table(self.invites_table).put_item(Item=invite_record)
        return invite_record

    def connect_parent(self, parent_user_id: str, invite_code: str) -> dict:
        if self.get_active_link_for_user(parent_user_id):
            raise HTTPException(
                status_code=409,
                detail="이미 연결된 가족이 있어 새 연결을 생성할 수 없습니다.",
            )

        invite_record = self._find_pending_invite_by_code(invite_code)
        if not invite_record:
            latest_same_code = self._find_latest_invite_by_code(invite_code)
            if latest_same_code and latest_same_code["status"] == "expired":
                raise HTTPException(status_code=400, detail="만료된 초대 코드입니다.")
            if latest_same_code and latest_same_code["status"] == "used":
                raise HTTPException(status_code=409, detail="이미 사용된 초대 코드입니다.")
            raise HTTPException(status_code=404, detail="유효한 초대 코드를 찾을 수 없습니다.")

        child_user_id = invite_record["child_user_id"]
        if child_user_id == parent_user_id:
            raise HTTPException(status_code=400, detail="본인 계정끼리는 연결할 수 없습니다.")

        if self.get_active_link_for_user(child_user_id):
            raise HTTPException(status_code=409, detail="이미 사용된 초대 코드입니다.")

        connected_at = datetime.now(timezone.utc)
        link_record = {
            "link_id": f"link_{uuid.uuid4().hex[:8]}",
            "parent_user_id": parent_user_id,
            "child_user_id": child_user_id,
            "status": "active",
            "created_at": connected_at.isoformat(),
            "connected_at": connected_at.isoformat(),
        }
        dynamodb_service.table(self.links_table).put_item(Item=link_record)
        dynamodb_service.table(self.invites_table).update_item(
            Key={"child_user_id": child_user_id, "created_at": invite_record["created_at"]},
            UpdateExpression="SET #s = :s, #u = :u",
            ExpressionAttributeNames={"#s": "status", "#u": "used_at"},
            ExpressionAttributeValues={
                ":s": "used",
                ":u": connected_at.isoformat(),
            },
        )
        return link_record

    def get_my_family(self, user_id: str, role: str | None) -> dict:
        if role == "child":
            self._expire_stale_invites_for_child(user_id)

        active_link = self.get_active_link_for_user(user_id)
        pending_invite = None
        if role == "child":
            pending_invite = self._get_pending_invite_for_child(user_id)

        return {
            "user_id": user_id,
            "role": role,
            "active_link": active_link,
            "pending_invite": pending_invite,
        }


class FamilyService:
    def __init__(self) -> None:
        self._memory_backend = InMemoryFamilyBackend()
        self._dynamodb_backend = DynamoDBFamilyBackend()
        self._backend_override = None

    def set_backend(self, backend) -> None:
        self._backend_override = backend

    def reset_backend(self) -> None:
        self._backend_override = None

    def _backend(self):
        if self._backend_override is not None:
            return self._backend_override
        if self._dynamodb_backend.is_configured():
            return self._dynamodb_backend
        if os.getenv("ALLOW_IN_MEMORY_FALLBACK", "").lower() == "true":
            return self._memory_backend
        raise HTTPException(
            status_code=500,
            detail="DynamoDB is not configured for family persistence.",
        )

    def _get_user_name(self, user_id: str | None) -> str | None:
        if not user_id or not dynamodb_service.is_configured():
            return None
        resp = dynamodb_service.table(
            os.getenv("DYNAMODB_USER_PROFILES_TABLE", "user_profiles")
        ).get_item(Key={"user_id": user_id})
        item = resp.get("Item")
        return item.get("name") if item else None

    def _enrich_active_link(self, active_link: dict | None) -> dict | None:
        if not active_link:
            return None
        enriched = dict(active_link)
        enriched["parent_name"] = self._get_user_name(enriched.get("parent_user_id"))
        enriched["child_name"] = self._get_user_name(enriched.get("child_user_id"))
        return enriched

    def create_invite(self, child_user_id: str) -> dict:
        return self._backend().create_invite(child_user_id)

    def connect_parent(self, parent_user_id: str, invite_code: str) -> dict:
        return self._backend().connect_parent(parent_user_id, invite_code)

    def get_my_family(self, user_id: str, role: str | None) -> dict:
        payload = self._backend().get_my_family(user_id, role)
        payload["active_link"] = self._enrich_active_link(payload.get("active_link"))
        return payload

    def get_active_link_for_user(self, user_id: str) -> dict | None:
        return self._backend().get_active_link_for_user(user_id)

    def get_linked_user_id(self, user_id: str) -> str | None:
        active_link = self.get_active_link_for_user(user_id)
        if not active_link:
            return None
        if active_link["child_user_id"] == user_id:
            return active_link["parent_user_id"]
        if active_link["parent_user_id"] == user_id:
            return active_link["child_user_id"]
        return None

    def require_linked_user_id(self, user_id: str) -> str:
        linked_user_id = self.get_linked_user_id(user_id)
        if not linked_user_id:
            raise HTTPException(status_code=409, detail="가족 연결이 필요합니다.")
        return linked_user_id


family_service = FamilyService()
