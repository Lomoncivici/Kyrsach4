from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone

class EmployeeManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email обязателен')
        email = self.normalize_email(email)
        employee = self.model(email=email, **extra_fields)
        employee.set_password(password)  # Это вызовет set_password ниже
        employee.save(using=self._db)
        return employee

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

class Employee(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True)
    email = models.EmailField(unique=True, verbose_name='Email')
    full_name = models.CharField(max_length=255, verbose_name='Полное имя')

    password = models.TextField(verbose_name='Хэш пароля', db_column='password_hash')

    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(verbose_name='Создан')
    updated_at = models.DateTimeField(verbose_name='Обновлен')

    is_staff = models.BooleanField(default=True, verbose_name='Доступ к админке')
    is_superuser = models.BooleanField(default=False, verbose_name='Суперпользователь')
    last_login = models.DateTimeField(auto_now=True, verbose_name='Последний вход')

    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name='employee_set',
        related_query_name='employee',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name='employee_set',
        related_query_name='employee',
    )
    
    objects = EmployeeManager()
    
    USERNAME_FIELD = 'email' 
    REQUIRED_FIELDS = ['full_name']
    
    class Meta:
        managed = False
        db_table = '"cinema"."employees"'
        verbose_name = 'Сотрудник'
        verbose_name_plural = 'Сотрудники'
    
    def __str__(self):
        return f'{self.full_name} ({self.email})'
    
    def has_perm(self, perm, obj=None):
        return self.is_superuser or self.is_staff
    
    def has_module_perms(self, app_label):
        return self.is_superuser or self.is_staff

    def set_password(self, raw_password):
        from django.contrib.auth.hashers import make_password
        self.password = make_password(raw_password)

    def get_roles(self):
        """Получает роли сотрудника из таблицы cinema.employee_roles"""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT r.code 
                FROM cinema.employee_roles er
                JOIN cinema.roles r ON r.id = er.role_id
                WHERE er.employee_id = %s
            """, [str(self.id)])
            return [row[0] for row in cursor.fetchall()]
    
    def has_role(self, role_code):
        """Проверяет есть ли у сотрудника определенная роль"""
        return role_code in self.get_roles()
    
    @property
    def password_hash(self):
        """Совместимость с существующим кодом"""
        return self.password
    
    @password_hash.setter
    def password_hash(self, value):
        """Совместимость с существующим кодом"""
        self.password = value

    def has_admin_role(self):
        """Проверка роли ADMIN (можно использовать в шаблоне)"""
        return 'ADMIN' in self.get_roles()
    
    def has_analyst_role(self):
        """Проверка роли ANALYST (можно использовать в шаблоне)"""
        return 'ANALYST' in self.get_roles()
    
    def has_support_role(self):
        """Проверка роли SUPPORT (можно использовать в шаблоне)"""
        return 'SUPPORT' in self.get_roles()