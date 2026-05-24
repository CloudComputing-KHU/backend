import random
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException


INVITE_TTL_MINUTES = 10
INVITE_CODE_LENGTH = 4
MAX_CODE_GENERATION_ATTEMPTS = 100

mock_family_invites: list[dict] = []
mock_family_links: list[dict] = []


class FamilyService:
    @staticmethod
    def _expire_stale_invites() -> None:
        now = datetime.now()
        for invite in mock_family_invites:
            if invite["status"] == "pending" and invite["expires_at"] < now:
                invite["status"] = "expired"

    @staticmethod
    def _get_active_link_for_user(user_id: str) -> dict | None:
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

        if self._get_active_link_for_user(child_user_id):
            raise HTTPException(
                status_code=409,
                detail="이미 연결된 가족이 있어 새 초대 코드를 생성할 수 없습니다.",
            )

        existing_invite = self._get_pending_invite_for_child(child_user_id)
        if existing_invite:
            return existing_invite

        created_at = datetime.now()
        invite_record = {
            "invite_code": self._generate_invite_code(),
            "child_user_id": child_user_id,
            "status": "pending",
            "created_at": created_at,
            "expires_at": created_at + timedelta(minutes=INVITE_TTL_MINUTES),
        }
        mock_family_invites.append(invite_record)
        return invite_record

    def connect_parent(self, parent_user_id: str, invite_code: str) -> dict:
        self._expire_stale_invites()

        if self._get_active_link_for_user(parent_user_id):
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

        if self._get_active_link_for_user(child_user_id):
            raise HTTPException(status_code=409, detail="이미 사용된 초대 코드입니다.")

        connected_at = datetime.now()
        link_record = {
            "link_id": f"link_{uuid.uuid4().hex[:8]}",
            "parent_user_id": parent_user_id,
            "child_user_id": child_user_id,
            "status": "active",
            "connected_at": connected_at,
        }
        mock_family_links.append(link_record)
        invite_record["status"] = "used"
        invite_record["used_at"] = connected_at
        return link_record

    def get_my_family(self, user_id: str, role: str | None) -> dict:
        self._expire_stale_invites()

        active_link = self._get_active_link_for_user(user_id)
        pending_invite = None
        if role == "child":
            pending_invite = self._get_pending_invite_for_child(user_id)

        return {
            "user_id": user_id,
            "role": role,
            "active_link": active_link,
            "pending_invite": pending_invite,
        }


family_service = FamilyService()
