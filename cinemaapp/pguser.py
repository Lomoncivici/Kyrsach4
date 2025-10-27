from uuid import UUID
from typing import Optional
from django.db import connection

def current_pg_user_uuid() -> Optional[UUID]:
    """
    Возвращает UUID из current_setting('app.user_id', true),
    который middleware ставит для авторизованного пользователя.
    """
    with connection.cursor() as cur:
        cur.execute("select current_setting('app.user_id', true)")
        row = cur.fetchone()
    val = row[0] if row else None
    return UUID(val) if val else None