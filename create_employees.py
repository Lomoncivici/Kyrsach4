# create_employees.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cinema_site.settings')
django.setup()

from django.db import connection
from django.contrib.auth.hashers import make_password
import uuid

# Данные сотрудников
employees_data = [
    {
        'id': str(uuid.uuid4()),
        'full_name': 'Главный Администратор',
        'email': 'admin@cinema.ru',
        'password': 'admin123',
        'roles': ['ADMIN']
    },
    {
        'id': str(uuid.uuid4()),
        'full_name': 'Аналитик Петрова',
        'email': 'analyst@cinema.ru', 
        'password': 'analyst123',
        'roles': ['ANALYST']
    },
    {
        'id': str(uuid.uuid4()),
        'full_name': 'Специалист Поддержки',
        'email': 'support@cinema.ru',
        'password': 'support123',
        'roles': ['SUPPORT']
    }
]

# Создаем сотрудников
with connection.cursor() as cursor:
    for emp in employees_data:
        # Генерируем Argon2 хэш пароля
        password_hash = make_password(emp['password'])
        
        # Вставляем сотрудника
        cursor.execute("""
            INSERT INTO cinema.employees (id, full_name, email, password_hash, is_active, created_at, updated_at)
            VALUES (%s, %s, %s, %s, true, NOW(), NOW())
            ON CONFLICT (email) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                password_hash = EXCLUDED.password_hash,
                updated_at = NOW()
        """, [emp['id'], emp['full_name'], emp['email'], password_hash])
        
        print(f"Создан сотрудник: {emp['email']}")
        
        # Назначаем роли
        for role_code in emp['roles']:
            cursor.execute("""
                INSERT INTO cinema.employee_roles (employee_id, role_id)
                SELECT %s, r.id
                FROM cinema.roles r
                WHERE r.code = %s
                ON CONFLICT DO NOTHING
            """, [emp['id'], role_code])
            
            print(f"  - Назначена роль: {role_code}")

print("\n✅ Сотрудники созданы!")
print("\nДанные для входа:")
for emp in employees_data:
    print(f"  {emp['email']} / {emp['password']}")