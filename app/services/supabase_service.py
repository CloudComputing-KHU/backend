import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()
logger = logging.getLogger(__name__)


class SupabaseService:
    def __init__(self) -> None:
        self._url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self._service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self._schema = os.getenv("SUPABASE_SCHEMA", "public")

    def is_configured(self) -> bool:
        return bool(self._url and self._service_role_key)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: list[tuple[str, str]] | None = None,
        payload: dict | list[dict] | None = None,
        prefer: str | None = None,
    ):
        if not self.is_configured():
            raise HTTPException(status_code=500, detail="Supabase is not configured.")

        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        url = f"{self._url}{path}{query}"

        headers = {
            "apikey": self._service_role_key,
            "Authorization": f"Bearer {self._service_role_key}",
            "Accept": "application/json",
            "Accept-Profile": self._schema,
            "Content-Profile": self._schema,
        }

        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if prefer:
            headers["Prefer"] = prefer

        request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            logger.exception("Supabase 요청 실패 - method=%s, path=%s, status=%s", method, path, exc.code)
            detail = raw
            try:
                parsed = json.loads(raw)
                detail = parsed.get("message") or parsed.get("error") or raw
            except json.JSONDecodeError:
                pass
            raise HTTPException(status_code=502, detail=f"Supabase request failed: {detail}") from exc
        except urllib.error.URLError as exc:
            logger.exception("Supabase 연결 실패 - method=%s, path=%s", method, path)
            raise HTTPException(status_code=502, detail=f"Supabase connection failed: {exc.reason}") from exc

    def select(
        self,
        table: str,
        *,
        filters: list[tuple[str, str]] | None = None,
        order: str | None = None,
        limit: int | None = None,
        columns: str = "*",
    ) -> list[dict]:
        params: list[tuple[str, str]] = [("select", columns)]
        if filters:
            params.extend(filters)
        if order:
            params.append(("order", order))
        if limit is not None:
            params.append(("limit", str(limit)))
        return self.request("GET", f"/rest/v1/{table}", params=params) or []

    def insert(self, table: str, payload: dict | list[dict]) -> list[dict]:
        return self.request(
            "POST",
            f"/rest/v1/{table}",
            payload=payload,
            prefer="return=representation",
        ) or []

    def upsert(self, table: str, payload: dict | list[dict], *, on_conflict: str) -> list[dict]:
        return self.request(
            "POST",
            f"/rest/v1/{table}",
            params=[("on_conflict", on_conflict)],
            payload=payload,
            prefer="resolution=merge-duplicates,return=representation",
        ) or []

    def update(self, table: str, *, filters: list[tuple[str, str]], payload: dict) -> list[dict]:
        return self.request(
            "PATCH",
            f"/rest/v1/{table}",
            params=filters,
            payload=payload,
            prefer="return=representation",
        ) or []


supabase_service = SupabaseService()
