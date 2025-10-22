from django.db import connection

class SetPgAppUser:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            with connection.cursor() as cur:
                cur.execute("SELECT set_config('app.user_id', %s, true);", [str(user.id)])
        return self.get_response(request)
