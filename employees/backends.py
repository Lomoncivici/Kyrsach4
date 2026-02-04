from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.hashers import check_password
from django.db import connection
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)

class EmployeeBackend(BaseBackend):
    """Бэкенд ТОЛЬКО для сотрудников. Никогда не пускает обычных пользователей."""
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        logger.info(f"EmployeeBackend checking: {username}")
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, email, full_name, password_hash, is_active 
                    FROM cinema.employees 
                    WHERE email = %s
                """, [username])
                
                row = cursor.fetchone()
                
                if not row:
                    logger.info(f"Not an employee: {username}")
                    return None
                
                emp_id, email, full_name, password_hash, is_active = row
                
                if not is_active:
                    logger.info(f"Employee inactive: {username}")
                    return None

                if not check_password(password, password_hash):
                    logger.info(f"Invalid employee password: {username}")
                    return None
                
                logger.info(f"Employee auth SUCCESS: {full_name}")
                

                employee_username = f"employee_{emp_id}"
                
                user, created = User.objects.get_or_create(
                    username=employee_username,
                    defaults={
                        'email': email,
                        'first_name': full_name,
                        'is_staff': False,
                        'is_active': True,
                        'password': '!',
                    }
                )
                

                request.session['is_employee'] = True
                request.session['employee_id'] = str(emp_id)
                request.session['employee_email'] = email
                request.session['employee_name'] = full_name

                cursor.execute("""
                    SELECT r.code 
                    FROM cinema.employee_roles er
                    JOIN cinema.roles r ON r.id = er.role_id
                    WHERE er.employee_id = %s
                """, [emp_id])
                
                roles = [r[0] for r in cursor.fetchall()]
                request.session['employee_roles'] = roles
                logger.info(f"Employee roles: {roles}")
                
                return user
                
        except Exception as e:
            logger.error(f"Error in EmployeeBackend: {e}", exc_info=True)
            return None
    
    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None