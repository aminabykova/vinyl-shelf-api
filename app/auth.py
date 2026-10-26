"""Заглушка авторизации.

В боевой системе токен JWT проверяет API Gateway. Здесь для тестирования принимается
токен вида `user-<число>`: `Authorization: Bearer user-1` означает пользователя с id=1.
"""
import re
from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .errors import unauthorized

_bearer = HTTPBearer(auto_error=False, description="Для заглушки используйте токен user-1, user-2 и т.д.")
_TOKEN = re.compile(r"^user-([1-9][0-9]*)$")


def current_user_id(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> int:
    if credentials is None:
        raise unauthorized()
    match = _TOKEN.match(credentials.credentials)
    if not match:
        raise unauthorized("Токен недействителен. В заглушке используйте токен вида user-1.")
    return int(match.group(1))
