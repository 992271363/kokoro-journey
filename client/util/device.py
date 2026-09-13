"""设备标识：客户端本地生成并持久化一个随机 device_id。

说明：
- device_id 仅用于标识设备（云同步单设备判定），**不是安全凭证**，鉴权仍靠 JWT。
- 存于 settings.json（明文）。
"""
import uuid

from util.config import Settings


def get_device_id() -> str:
    s = Settings()
    did = s.get("cloudDeviceId")
    if not did:
        did = uuid.uuid4().hex
        s.set("cloudDeviceId", did)
    return did
