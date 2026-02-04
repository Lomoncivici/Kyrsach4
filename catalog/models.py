from django.utils import timezone
from datetime import timedelta
from django.db import models
from django.contrib.auth.models import User
from cinemaapp.models import Content

class CinemaUser(models.Model):
    """Связь с cinema.users"""
    id = models.UUIDField(primary_key=True)
    email = models.TextField(unique=True)
    login = models.TextField(unique=True)
    password_hash = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = '"cinema"."users"'
        verbose_name = "Пользователь Cinema"
        verbose_name_plural = "Пользователи Cinema"

class SubscriptionPlan(models.Model):
    """План подписки из cinema.subscription_plans"""
    id = models.UUIDField(primary_key=True)
    code = models.TextField(unique=True)
    name = models.TextField()
    period_months = models.IntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = '"cinema"."subscription_plans"'
        verbose_name = "План подписки"
        verbose_name_plural = "Планы подписок"

    def __str__(self):
        return f"{self.name} - {self.price} руб."

class UserSubscription(models.Model):
    """Подписка пользователя из cinema.user_subscriptions"""
    id = models.UUIDField(primary_key=True)
    user = models.ForeignKey(CinemaUser, on_delete=models.CASCADE, db_column='user_id')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.RESTRICT, db_column='plan_id')
    status = models.TextField()
    started_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = '"cinema"."user_subscriptions"'
        verbose_name = "Подписка пользователя"
        verbose_name_plural = "Подписки пользователей"
        unique_together = [['user', 'plan', 'started_at']]

    def __str__(self):
        return f"{self.user.login} - {self.plan.name} ({self.status})"
    
    def check_is_active(self):
        """Проверка активности подписки (возвращает bool)"""
        from django.utils import timezone
        return (
            self.status == 'active' and 
            self.expires_at is not None and 
            self.expires_at > timezone.now()
        )
    
    @property
    def valid_until(self):
        """Совместимость с шаблоном"""
        return self.expires_at
    
    @property
    def plan_title(self):
        """Совместимость с шаблоном"""
        return self.plan.name
    
    @property
    def is_expired_soon(self):
        """Подписка скоро истекает (менее 7 дней)"""
        days_left = self.days_until_expire
        if days_left and 0 < days_left <= 7:
            return True
        return False
    
    @property
    def status_display(self):
        """Отображаемый статус с учетом даты окончания"""
        if self.status == 'active':
            if self.days_until_expire is not None:
                if self.days_until_expire > 0:
                    return 'active'
                else:
                    return 'expired'
            return 'active'
        return self.status
    
    def get_actual_status(self):
        """Возвращает фактический статус с учетом даты"""
        if self.status == 'cancelled':
            return 'cancelled'
        
        if self.expires_at:
            if self.expires_at > timezone.now():
                return 'active'
            else:
                return 'expired'

        if self.status == 'active':
            return 'active'
        
        return self.status
    
    @property
    def is_actually_active(self):
        """Проверяет, активна ли подписка на данный момент"""
        now = timezone.now()
        return (
            self.status == 'active' and 
            (

                (self.expires_at is None or self.expires_at > now)
                or

                (self.started_at and self.started_at > now)
            )
        )
    
    @property
    def days_left(self):
        """Количество дней до окончания подписки"""
        if self.expires_at:
            now = timezone.now()
            if self.expires_at > now:
                delta = self.expires_at - now
                return delta.days
        return 0
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
    
    def calculate_expiry_date(self):
        """Рассчитывает дату окончания подписки"""
        if not self.started_at:
            self.started_at = timezone.now()
        

        from dateutil.relativedelta import relativedelta
        self.expires_at = self.started_at + relativedelta(months=self.plan.period_months)
        return self.expires_at
    
    @property
    def can_be_cancelled(self):
        """Можно ли отменить подписку (до 14 дней с начала)"""
        if not self.started_at:
            return False
        
        days_since_start = (timezone.now() - self.started_at).days
        return days_since_start <= 14 and self.status == 'active' and self.expires_at > timezone.now()
    
    @property
    def days_since_start(self):
        """Дней с начала подписки"""
        if not self.started_at:
            return 0
        return (timezone.now() - self.started_at).days
    
    @property
    def will_be_extended(self):
        """Будет ли продлена текущая подписка"""

        return UserSubscription.get_active_subscriptions(self.user).exclude(id=self.id).exists()
    
    @classmethod
    def get_active_subscriptions(cls, user):
        """Возвращает все активные подписки пользователя (текущие + будущие)"""
        from django.db.models import Q
        
        now = timezone.now()
        return cls.objects.filter(
            user=user,
            status='active'
        ).filter(
            Q(
 
                Q(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            ) |
            Q(

                started_at__gt=now
            )
        )
    
    @property
    def is_actually_active_now(self):
        """Проверяет, активна ли подписка СЕЙЧАС"""
        from django.utils import timezone
        return (
            self.status == 'active' and 
            self.started_at <= timezone.now() and
            (self.expires_at is None or self.expires_at > timezone.now())
        )
    
    @classmethod
    def get_current_active_subscription(cls, user):
        """Возвращает текущую активную подписку (которая действует прямо сейчас)"""
        from django.utils import timezone
        from django.db.models import Q
        
        now = timezone.now()
        return cls.objects.filter(
            user=user,
            status='active',
            started_at__lte=now,
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).order_by('-expires_at').first()
    
    @classmethod
    def get_future_subscriptions(cls, user):
        """Возвращает будущие подписки (которые еще не начались)"""
        from django.utils import timezone
        now = timezone.now()
        
        return cls.objects.filter(
            user=user,
            status='active',
            started_at__gt=now
        ).order_by('started_at')
    
    @classmethod
    def get_all_active_subscriptions(cls, user):
        """Возвращает все активные подписки (текущие + будущие)"""
        from django.utils import timezone
        from django.db.models import Q
        
        now = timezone.now()
        return cls.objects.filter(
            user=user,
            status='active'
        ).filter(
            Q(

                Q(started_at__lte=now) & 
                Q(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            ) |
            Q(

                started_at__gt=now
            )
        ).order_by('-started_at')

class Purchase(models.Model):
    """Покупка контента из cinema.purchases"""
    id = models.UUIDField(primary_key=True)
    user = models.ForeignKey(CinemaUser, on_delete=models.CASCADE, db_column='user_id')
    content = models.ForeignKey(Content, on_delete=models.RESTRICT, db_column='content_id')
    purchased_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = '"cinema"."purchases"'
        verbose_name = "Покупка контента"
        verbose_name_plural = "Покупки контента"
        unique_together = [['user', 'content']]

    def __str__(self):
        return f"{self.user.login} - {self.content.title}"

class Payment(models.Model):
    """Платежи из cinema.payments"""
    id = models.UUIDField(primary_key=True)
    txn_uuid = models.CharField(unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.TextField()
    paid_at = models.DateTimeField(null=True, blank=True)
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, null=True, blank=True, db_column='purchase_id')
    subscription = models.ForeignKey(UserSubscription, on_delete=models.CASCADE, null=True, blank=True, db_column='subscription_id')
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = '"cinema"."payments"'
        verbose_name = "Платеж"
        verbose_name_plural = "Платежи"

    def __str__(self):
        return f"{self.amount} руб. - {self.status}"