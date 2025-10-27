from django.db import connection

class SetPgAppUser:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            with connection.cursor() as cur:
                # маппинг auth_user -> cinema.users (UUID)
                cur.execute("SELECT id FROM cinema.users WHERE login=%s", [user.username])
                row = cur.fetchone()
                if row is None:
                    # создание записи в cinema.users
                    cur.execute("""
                        INSERT INTO cinema.users (login, email, password_hash, is_active)
                        VALUES (%s, %s, %s, TRUE)
                        RETURNING id
                    """, [user.username or f"user{user.id}", (user.email or f"{user.username}@local.test"), "$argon2"])
                    row = cur.fetchone()
                cur.execute("SELECT set_config('app.user_id', %s, true);", [str(row[0])])
        return self.get_response(request)
