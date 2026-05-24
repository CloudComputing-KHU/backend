import os
import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.services.supabase_service import supabase_service

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


class SupabaseFamilyBackend:
    @staticmethod
    def is_configured() -> bool:
        return supabase_service.is_configured()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _table_name(env_name: str, default: str) -> str:
        import os

        return os.getenv(env_name, default)

    @property
    def invites_table(self) -> str:
        return self._table_name("SUPABASE_FAMILY_INVITES_TABLE", "family_invites")

    @property
    def links_table(self) -> str:
        return self._table_name("SUPABASE_FAMILY_LINKS_TABLE", "family_links")

    def _select(
        self,
        table: str,
        *,
        filters: list[tuple[str, str]],
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        params = [("select", "*"), *filters]
        if order:
            params.append(("order", order))
        if limit is not None:
            params.append(("limit", str(limit)))
        result = supabase_service.request("GET", f"/rest/v1/{table}", params=params)
        return result or []

    def _insert(self, table: str, payload: dict) -> dict:
        result = supabase_service.request(
            "POST",
            f"/rest/v1/{table}",
            payload=payload,
            prefer="return=representation",
        )
        if not result:
            raise HTTPException(status_code=502, detail="Supabase insert failed.")
        return result[0]

    def _update(self, table: str, *, filters: list[tuple[str, str]], payload: dict) -> list[dict]:
        result = supabase_service.request(
            "PATCH",
            f"/rest/v1/{table}",
            params=filters,
            payload=payload,
            prefer="return=representation",
        )
        return result or []

    def _expire_stale_invites(self) -> None:
        self._update(
            self.invites_table,
            filters=[
                ("status", "eq.pending"),
                ("expires_at", f"lt.{self._utc_now_iso()}"),
            ],
            payload={"status": "expired"},
        )

    def get_active_link_for_user(self, user_id: str) -> dict | None:
        links = self._select(
            self.links_table,
            filters=[
                ("status", "eq.active"),
                ("or", f"(parent_user_id.eq.{user_id},child_user_id.eq.{user_id})"),
            ],
            order="connected_at.desc",
            limit=1,
        )
        return links[0] if links else None

    def _get_pending_invite_for_child(self, child_user_id: str) -> dict | None:
        invites = self._select(
            self.invites_table,
            filters=[
                ("child_user_id", f"eq.{child_user_id}"),
                ("status", "eq.pending"),
            ],
            order="created_at.desc",
            limit=1,
        )
        return invites[0] if invites else None

    def _find_pending_invite_by_code(self, invite_code: str) -> dict | None:
        invites = self._select(
            self.invites_table,
            filters=[
                ("invite_code", f"eq.{invite_code}"),
                ("status", "eq.pending"),
            ],
            order="created_at.desc",
            limit=1,
        )
        return invites[0] if invites else None

    def _find_latest_invite_by_code(self, invite_code: str) -> dict | None:
        invites = self._select(
            self.invites_table,
            filters=[("invite_code", f"eq.{invite_code}")],
            order="created_at.desc",
            limit=1,
        )
        return invites[0] if invites else None

    def _generate_invite_code(self) -> str:
        for _ in range(MAX_CODE_GENERATION_ATTEMPTS):
            invite_code = f"{random.randint(0, 9999):0{INVITE_CODE_LENGTH}d}"
            exists = self._select(
                self.invites_table,
                filters=[
                    ("invite_code", f"eq.{invite_code}"),
                    ("status", "eq.pending"),
                ],
                limit=1,
            )
            if not exists:
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

        created_at = datetime.now(timezone.utc)
        invite_record = {
            "invite_id": f"invite_{uuid.uuid4().hex[:8]}",
            "invite_code": self._generate_invite_code(),
            "child_user_id": child_user_id,
            "status": "pending",
            "created_at": created_at.isoformat(),
            "expires_at": (created_at + timedelta(minutes=INVITE_TTL_MINUTES)).isoformat(),
            "used_at": None,
        }
        return self._insert(self.invites_table, invite_record)

    def connect_parent(self, parent_user_id: str, invite_code: str) -> dict:
        self._expire_stale_invites()

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
        created_link = self._insert(self.links_table, link_record)
        self._update(
            self.invites_table,
            filters=[("invite_id", f"eq.{invite_record['invite_id']}")],
            payload={
                "status": "used",
                "used_at": connected_at.isoformat(),
            },
        )
        return created_link

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


class FamilyService:
    def __init__(self) -> None:
        self._memory_backend = InMemoryFamilyBackend()
        self._supabase_backend = SupabaseFamilyBackend()
        self._backend_override = None

    def set_backend(self, backend) -> None:
        self._backend_override = backend

    def reset_backend(self) -> None:
        self._backend_override = None

    def _backend(self):
        if self._backend_override is not None:
            return self._backend_override
        if self._supabase_backend.is_configured():
            return self._supabase_backend
        return self._memory_backend

    @property
    def _user_profiles_table(self) -> str:
        return os.getenv("SUPABASE_USER_PROFILES_TABLE", "user_profiles")

    def _get_user_name(self, user_id: str | None, *, use_supabase: bool) -> str | None:
        if not user_id or not use_supabase or not supabase_service.is_configured():
            return None
        rows = supabase_service.select(
            self._user_profiles_table,
            filters=[("user_id", f"eq.{user_id}")],
            limit=1,
        )
        if not rows:
            return None
        return rows[0].get("name")

    def _enrich_active_link(self, active_link: dict | None, *, use_supabase: bool) -> dict | None:
        if not active_link:
            return None
        enriched = dict(active_link)
        enriched["parent_name"] = self._get_user_name(
            enriched.get("parent_user_id"),
            use_supabase=use_supabase,
        )
        enriched["child_name"] = self._get_user_name(
            enriched.get("child_user_id"),
            use_supabase=use_supabase,
        )
        return enriched

    def create_invite(self, child_user_id: str) -> dict:
        return self._backend().create_invite(child_user_id)

    def connect_parent(self, parent_user_id: str, invite_code: str) -> dict:
        return self._backend().connect_parent(parent_user_id, invite_code)

    def get_my_family(self, user_id: str, role: str | None) -> dict:
        backend = self._backend()
        payload = backend.get_my_family(user_id, role)
        payload["active_link"] = self._enrich_active_link(
            payload.get("active_link"),
            use_supabase=backend is self._supabase_backend,
        )
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
