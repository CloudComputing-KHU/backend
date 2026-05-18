from pydantic import BaseModel


class DeviceRegisterRequest(BaseModel):
    fcm_token: str


class DeviceRegisterResponse(BaseModel):
    message: str
