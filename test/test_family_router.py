from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app
from app.services.auth_service import get_current_user
from app.services.family_service import mock_family_invites, mock_family_links

client = TestClient(app)

CHILD_USER = {
    "sub": "child_001",
    "email": "child@test.com",
    "custom:role": "child",
}
PARENT_USER = {
    "sub": "parent_001",
    "email": "parent@test.com",
    "custom:role": "parent",
}


def setup_function() -> None:
    mock_family_invites.clear()
    mock_family_links.clear()
    app.dependency_overrides.clear()


def test_family_invite_and_connect_flow() -> None:
    app.dependency_overrides[get_current_user] = lambda: CHILD_USER
    invite_response = client.post("/family/invites")

    assert invite_response.status_code == 200
    invite_payload = invite_response.json()
    assert invite_payload["child_user_id"] == "child_001"
    assert invite_payload["status"] == "pending"
    assert invite_payload["invite_code"].isdigit()
    assert len(invite_payload["invite_code"]) == 4

    me_child_response = client.get("/family/me")
    assert me_child_response.status_code == 200
    assert me_child_response.json()["pending_invite"]["invite_code"] == invite_payload["invite_code"]

    app.dependency_overrides[get_current_user] = lambda: PARENT_USER
    connect_response = client.post(
        "/family/connect",
        json={"invite_code": invite_payload["invite_code"]},
    )

    assert connect_response.status_code == 200
    connect_payload = connect_response.json()
    assert connect_payload["parent_user_id"] == "parent_001"
    assert connect_payload["child_user_id"] == "child_001"
    assert connect_payload["status"] == "active"

    me_parent_response = client.get("/family/me")
    assert me_parent_response.status_code == 200
    parent_payload = me_parent_response.json()
    assert parent_payload["role"] == "parent"
    assert parent_payload["active_link"]["child_user_id"] == "child_001"

    app.dependency_overrides[get_current_user] = lambda: CHILD_USER
    me_child_after_connect = client.get("/family/me")
    assert me_child_after_connect.status_code == 200
    child_payload = me_child_after_connect.json()
    assert child_payload["active_link"]["parent_user_id"] == "parent_001"
    assert child_payload["pending_invite"] is None


def test_family_role_restrictions() -> None:
    app.dependency_overrides[get_current_user] = lambda: PARENT_USER
    parent_invite_response = client.post("/family/invites")
    assert parent_invite_response.status_code == 403

    app.dependency_overrides[get_current_user] = lambda: CHILD_USER
    child_connect_response = client.post("/family/connect", json={"invite_code": "1234"})
    assert child_connect_response.status_code == 403
