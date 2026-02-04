from django.utils import timezone
from django.core.cache import cache
import secrets
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from cinemaapp.models import Content

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=32, blank=True, null=True)

    def __str__(self):
        return f"Profile({self.user.username})"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

class PasswordResetCode(models.Model):
    """Модель для хранения кодов сброса пароля (временное, можно использовать кэш)"""
    
    @staticmethod
    def generate_code(user_id, email):
        """Генерирует 6-значный код и сохраняет его"""
        code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        
        cache_key = f'password_reset_code_{user_id}_{email}'
        
        # Сохраняем в кэш на время
        cache.set(cache_key, {
            'code': code,
            'user_id': user_id,
            'email': email,
            'created_at': timezone.now().isoformat()
        }, 120)
        
        return code
    
    @staticmethod
    def verify_code(user_id, email, code):
        """Проверяет код"""
        cache_key = f'password_reset_code_{user_id}_{email}'
        data = cache.get(cache_key)
        
        if not data:
            return False
        
        if data['code'] == code:
            # Удаляем код после успешной проверки
            cache.delete(cache_key)
            return True
        
        return False
    
    @staticmethod
    def clear_code(user_id, email):
        """Удаляет код"""
        cache_key = f'password_reset_code_{user_id}_{email}'
        cache.delete(cache_key)


class PasswordResetToken(models.Model):
    """Модель для хранения токенов сброса пароля (для неавторизованных)"""
    
    @staticmethod
    def create_token(user_id, email):
        """Создает уникальный токен для сброса пароля"""
        from django.utils import timezone
        from django.core.cache import cache
        import uuid
        import hashlib
        
        # Генерируем уникальный токен
        token = str(uuid.uuid4())
        
        # Создаем ключ для кэша
        cache_key = f'password_reset_token_{token}'
        
        # Сохраняем в кэш на впемя
        cache.set(cache_key, {
            'user_id': user_id,
            'email': email,
            'created_at': timezone.now().isoformat()
        }, 300)
        
        return token
    
    @staticmethod
    def get_token_data(token):
        """Получает данные по токену"""
        from django.core.cache import cache
        
        cache_key = f'password_reset_token_{token}'
        return cache.get(cache_key)
    
    @staticmethod
    def delete_token(token):
        """Удаляет токен"""
        from django.core.cache import cache
        
        cache_key = f'password_reset_token_{token}'
        cache.delete(cache_key)