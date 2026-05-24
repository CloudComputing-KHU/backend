from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


InviteStatus = Literal["pending", "used", "expired"]
LinkStatus = Literal["active"]
UserRole = Literal["child", "parent"]


class FamilyConnectRequest(BaseModel):
    invite_code: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")


class FamilyInviteResponse(BaseModel):
    message: str
    invite_code: str
    child_user_id: str
    status: InviteStatus
    created_at: datetime
    expires_at: datetime


class FamilyLinkResponse(BaseModel):
    message: str
    link_id: str
    parent_user_id: str
    child_user_id: str
    status: LinkStatus
    connected_at: datetime


class FamilyInviteItem(BaseModel):
    invite_code: str
    child_user_id: str
    status: InviteStatus
    created_at: datetime
    expires_at: datetime


class FamilyLinkItem(BaseModel):
    link_id: str
    parent_user_id: str
    child_user_id: str
    parent_name: Optional[str] = None
    child_name: Optional[str] = None
    status: LinkStatus
    connected_at: datetime


class FamilyMeResponse(BaseModel):
    user_id: str
    role: Optional[UserRole] = None
    active_link: Optional[FamilyLinkItem] = None
    pending_invite: Optional[FamilyInviteItem] = None
