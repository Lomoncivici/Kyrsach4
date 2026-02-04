from django.contrib import admin
from django import forms
import uuid
from django.utils.html import format_html
from .models import *


class MediaAssetForm(forms.ModelForm):
    class Meta:
        model = MediaAsset
        fields = ['kind', 'mime_type', 'url']
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.id:
            instance.id = uuid.uuid4()
        if commit:
            instance.save()
        return instance

class ContentForm(forms.ModelForm):

    cover_url = forms.URLField(
        required=False,
        label='URL обложки',
        help_text='Пример: https://example.com/poster.jpg'
    )
    trailer_url = forms.URLField(
        required=False,
        label='URL трейлера',
        help_text='Пример: https://example.com/trailer.mp4'
    )
    
    class Meta:
        model = Content
        fields = '__all__'


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    form = MediaAssetForm
    list_display = ('kind', 'mime_type', 'url_short', 'preview')
    list_filter = ('kind', 'mime_type')
    search_fields = ('url',)
    
    def url_short(self, obj):
        if len(obj.url) > 50:
            return obj.url[:50] + '...'
        return obj.url
    url_short.short_description = 'URL'
    
    def preview(self, obj):
        if obj.mime_type.startswith('image/'):
            return format_html('<img src="{}" style="max-height: 50px;" />', obj.url)
        return '-'
    preview.short_description = 'Предпросмотр'
    
    def save_model(self, request, obj, form, change):
        if not obj.id:
            obj.id = uuid.uuid4()
        super().save_model(request, obj, form, change)

    def save(self, *args, **kwargs):
        """Автоматическая генерация UUID"""
        if not self.id:
            import uuid
            self.id = uuid.uuid4()
        super().save(*args, **kwargs)

@admin.register(Content)
class ContentAdmin(admin.ModelAdmin):
    form = ContentForm
    list_display = ('title', 'type', 'release_year', 'is_free', 'price')
    list_filter = ('type', 'is_free', 'release_year')
    search_fields = ('title', 'description')
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('type', 'title', 'release_year', 'description', 'is_free', 'price')
        }),
        ('Быстрое добавление медиа (через URL)', {
            'fields': ('cover_url', 'trailer_url'),
            'description': 'Вставьте ссылки - MediaAsset будут созданы автоматически'
        }),
        ('Выбор существующих MediaAsset', {
            'fields': ('cover_image', 'cover_image_wide', 'trailer', 'video'),
            'classes': ('collapse',),
        }),
    )
    
    def save_model(self, request, obj, form, change):

        if not obj.id:
            obj.id = uuid.uuid4()
        

        cover_url = form.cleaned_data.get('cover_url')
        if cover_url:
            obj.cover_image = MediaAsset.objects.create(
                id=uuid.uuid4(),
                kind='cover',
                mime_type='image/jpeg',
                url=cover_url
            )
        
        trailer_url = form.cleaned_data.get('trailer_url')
        if trailer_url:
            obj.trailer = MediaAsset.objects.create(
                id=uuid.uuid4(),
                kind='trailer',
                mime_type='video/mp4',
                url=trailer_url
            )
        
        super().save_model(request, obj, form, change)


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(ContentGenre)
class ContentGenreAdmin(admin.ModelAdmin):
    list_display = ('content', 'genre')
    search_fields = ('content__title', 'genre__name')
    raw_id_fields = ('content', 'genre')

@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ('content', 'season_num')
    search_fields = ('content__title',)
    raw_id_fields = ('content',)

@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    list_display = ('season', 'episode_num', 'title')
    search_fields = ('title', 'season__content__title')
    raw_id_fields = ('season', 'video')

@admin.register(CinemaUser)
class CinemaUserAdmin(admin.ModelAdmin):
    list_display = ('login', 'email', 'is_active')
    search_fields = ('login', 'email')

@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'content', 'created_at')
    search_fields = ('user__login', 'content__title')
    raw_id_fields = ('user', 'content')

@admin.register(Watchlist)
class WatchlistAdmin(admin.ModelAdmin):
    list_display = ('user', 'content', 'created_at')
    search_fields = ('user__login', 'content__title')
    raw_id_fields = ('user', 'content')

@admin.register(WatchHistory)
class WatchHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'content', 'episode', 'watched_at')
    search_fields = ('user__login', 'content__title')
    raw_id_fields = ('user', 'content', 'episode')

@admin.register(VContentWithRating)
class VContentWithRatingAdmin(admin.ModelAdmin):
    list_display = ('title', 'type', 'release_year', 'avg_rating')
    search_fields = ('title',)
    
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(ContentReview)
class ContentReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'content', 'rating', 'created_at')
    search_fields = ('user__login', 'content__title', 'comment')
    raw_id_fields = ('user', 'content')