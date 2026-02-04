from django.contrib import admin
from .models import (
    CinemaUser, SubscriptionPlan, UserSubscription, 
    Purchase, Payment
)

@admin.register(CinemaUser)
class CinemaUserAdmin(admin.ModelAdmin):
    list_display = ('login', 'email', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('login', 'email')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        ('Основная информация', {
            'fields': ('id', 'login', 'email', 'password_hash')
        }),
        ('Статус', {
            'fields': ('is_active',)
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'period_months', 'price', 'is_active')
    list_filter = ('is_active', 'period_months')
    search_fields = ('name', 'code')
    readonly_fields = ('id', 'created_at')
    fieldsets = (
        ('Основная информация', {
            'fields': ('id', 'code', 'name')
        }),
        ('Параметры подписки', {
            'fields': ('period_months', 'price')
        }),
        ('Статус', {
            'fields': ('is_active',)
        }),
        ('Даты', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'started_at', 'expires_at', 'is_actually_active')
    list_filter = ('status', 'plan', 'started_at')
    search_fields = ('user__login', 'user__email', 'plan__name')
    readonly_fields = ('id', 'is_actually_active', 'days_left')
    raw_id_fields = ('user', 'plan')
    
    def is_actually_active(self, obj):
        return obj.is_actually_active
    is_actually_active.short_description = 'Активна сейчас'
    is_actually_active.boolean = True

@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('user', 'content', 'purchased_at')
    list_filter = ('purchased_at',)
    search_fields = ('user__login', 'content__title')
    readonly_fields = ('id', 'purchased_at')
    raw_id_fields = ('user', 'content')
    date_hierarchy = 'purchased_at'

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('txn_uuid', 'amount', 'status', 'paid_at', 'created_at')
    list_filter = ('status', 'paid_at', 'created_at')
    search_fields = ('txn_uuid', 'amount')
    readonly_fields = ('id', 'txn_uuid', 'created_at')
    raw_id_fields = ('purchase', 'subscription')
    fieldsets = (
        ('Основная информация', {
            'fields': ('id', 'txn_uuid', 'amount', 'status')
        }),
        ('Даты', {
            'fields': ('paid_at', 'created_at')
        }),
        ('Связанные объекты', {
            'fields': ('purchase', 'subscription'),
            'classes': ('collapse',)
        }),
    )