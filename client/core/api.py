import os
from pathlib import Path
import requests
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1").rstrip('/')
API_URL = f"{BASE_URL}/api"

#定义一个清晰的登录状态枚举
class LoginStatus(Enum):
    SUCCESS = 0
    INVALID_CREDENTIALS = 1 # 用户名或密码无效
    NETWORK_ERROR = 2       # 网络问题，如无法连接、超时
    UNKNOWN_ERROR = 3       # 其他未知错误

def api_login(username: str, password: str) -> Tuple[LoginStatus, Optional[str]]:
    """
    调用后端接口进行登录，并返回详细的状态。

    Returns:
        一个元组 (LoginStatus, token)，其中 token 只在成功时有效。
    """
    login_url = f"{API_URL}/auth/token"

    try:
        response = requests.post(
            login_url,
            data={"username": username, "password": password},
            timeout=10
        )
        # 检查是否为 HTTP 错误 (4xx, 5xx)
        response.raise_for_status() 

        access_token = response.json().get("access_token")
        if access_token:
            return (LoginStatus.SUCCESS, access_token)
        else:
            # 成功响应但没有 token，视为未知错误
            print(f"登录API响应成功，但响应体中缺少 'access_token': {response.text}")
            return (LoginStatus.UNKNOWN_ERROR, None)

    #异常处理逻辑
    except requests.exceptions.HTTPError as e:
        # 特别处理 HTTP 错误
        # FastAPI 在用户名密码错误时，默认返回 400 Bad Request
        if e.response.status_code == 400 or e.response.status_code == 401:
            # 这是明确的凭证错误
            return (LoginStatus.INVALID_CREDENTIALS, None)
        else:
            # 其他 HTTP 错误（如 404, 500）也归为网络或服务器问题
            print(f"登录API请求失败，HTTP 错误: {e}")
            return (LoginStatus.NETWORK_ERROR, None)
            
    except requests.exceptions.RequestException as e:
        # 处理所有其他网络相关的异常 (连接超时, DNS错误, 连接被拒绝等)
        print(f"登录API请求失败，底层网络错误: {e}")
        return (LoginStatus.NETWORK_ERROR, None)

def send_data_to_api(data_list: List[Dict[str, Any]], endpoint: str, token: str) -> bool:
    if not data_list:
        return True

    target_url = f"{API_URL}/{endpoint.lstrip('/')}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.post(target_url, json=data_list, headers=headers, timeout=5) #可以调整超时时间
        response.raise_for_status()
        print(f"成功发送 {len(data_list)} 条数据到 {endpoint}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"发送数据到 {endpoint} 失败: {e}")
        return False
