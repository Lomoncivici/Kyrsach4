from django.db import connection

class SetPgAppUser:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'session') and request.session.get('is_employee'):
            employee_id = request.session.get('employee_id')
            if employee_id:
                try:
                    with connection.cursor() as cur:
                        cur.execute("SELECT set_config('app.user_id', %s, true);", [employee_id])
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.debug(f"Could not set app.user_id for employee: {e}")
            return self.get_response(request)

        if hasattr(request, 'session'):
            user = getattr(request, "user", None)
            if user and user.is_authenticated and not request.session.get('is_employee'):
                try:
                    with connection.cursor() as cur:
                        cur.execute("SELECT id FROM cinema.users WHERE email=%s OR login=%s", 
                                   [user.email, user.username])
                        row = cur.fetchone()
                        
                        if row:
                            cur.execute("SELECT set_config('app.user_id', %s, true);", [str(row[0])])
                        else:

                            cur.execute("SELECT set_config('app.user_id', '', true);")
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.debug(f"Could not set app.user_id for regular user: {e}")
        
        return self.get_response(request)

class UserTypeMiddleware:
    """
    Middleware для определения типа пользователя (сотрудник/пользователь)
    и установки настроек PostgreSQL.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if hasattr(request, 'session'):
            request.is_employee = request.session.get('is_employee', False)
            request.employee_roles = request.session.get('employee_roles', [])

        if hasattr(request, 'session') and hasattr(request, 'user'):
            user = request.user
            if user and user.is_authenticated:
                try:
                    with connection.cursor() as cur:

                        cur.execute("SELECT id FROM cinema.users WHERE email=%s OR login=%s", 
                                   [user.email, user.username])
                        row = cur.fetchone()
                        
                        if row:
                            cur.execute("SELECT set_config('app.user_id', %s, true);", [str(row[0])])
                        else:

                            cur.execute("SELECT set_config('app.user_id', '', true);")
                except Exception as e:

                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error setting PostgreSQL user_id: {e}")
        
        response = self.get_response(request)
        return response