from django.db import models
from django.conf import settings

def t(name: str) -> str:
    return f'"cinema"."{name}"'

class MediaAsset(models.Model):
    id = models.UUIDField(primary_key=True)
    kind = models.CharField(max_length=16)
    mime_type = models.CharField(max_length=64)
    url = models.TextField(unique=True)
    class Meta:
        managed = False
        db_table = t("media_assets")

class Content(models.Model):
    id = models.UUIDField(primary_key=True)
    type = models.CharField(max_length=12)  # movie/series
    title = models.TextField(unique=True)
    release_year = models.IntegerField()
    description = models.TextField()
    is_free = models.BooleanField(default=False)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cover_image = models.ForeignKey(MediaAsset, null=True, on_delete=models.SET_NULL,
                                    db_column="cover_image_id", related_name="as_cover_for")
    cover_image_wide = models.ForeignKey(
        MediaAsset, null=True, on_delete=models.SET_NULL,
        db_column="cover_image_wide_id", related_name="as_wide_cover_for"
    )
    trailer = models.ForeignKey(MediaAsset, null=True, on_delete=models.SET_NULL,
                                db_column="trailer_id", related_name="as_trailer_for")
    video = models.ForeignKey(MediaAsset, null=True, on_delete=models.SET_NULL,
                              db_column="video_id", related_name="as_video_for")
    
    created_at = models.DateTimeField(db_column='created_at')
    updated_at = models.DateTimeField(db_column='updated_at')
    class Meta:
        managed = False
        db_table = t("content")

class Genre(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.TextField(unique=True)
    class Meta:
        managed = False
        db_table = t("genres")

class ContentGenre(models.Model):
    content = models.ForeignKey(
        Content, on_delete=models.DO_NOTHING, db_column="content_id", primary_key=True
    )
    genre = models.ForeignKey(
        Genre, on_delete=models.DO_NOTHING, db_column="genre_id"
    )
    class Meta:
        managed = False
        db_table = t("content_genres")
        unique_together = (("content","genre"),)

class Season(models.Model):
    id = models.UUIDField(primary_key=True)
    content = models.ForeignKey(Content, on_delete=models.CASCADE, db_column="content_id")
    season_num = models.IntegerField(db_column='season_num')
    class Meta:
        managed = False
        db_table = t("seasons")

class Episode(models.Model):
    id = models.UUIDField(primary_key=True)
    season = models.ForeignKey(Season, on_delete=models.CASCADE, db_column="season_id")
    episode_num = models.IntegerField()
    title = models.TextField()
    duration_sec = models.IntegerField()
    video = models.ForeignKey(MediaAsset, null=True, on_delete=models.SET_NULL, db_column="video_id")
    class Meta:
        managed = False
        db_table = t("episodes")

class CinemaUser(models.Model):
    id = models.UUIDField(primary_key=True)
    login = models.TextField(unique=True)
    email = models.TextField(null=True)
    is_active = models.BooleanField(default=True)
    class Meta:
        managed = False
        db_table = t("users")

class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites')
    content = models.ForeignKey('catalog.Content', on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'content')
        indexes = [models.Index(fields=['user', 'content'])]
    
    user = models.ForeignKey(
        CinemaUser, on_delete=models.DO_NOTHING, db_column="user_id", primary_key=True
    )
    content = models.ForeignKey(
        Content, on_delete=models.DO_NOTHING, db_column="content_id"
    )
    created_at = models.DateTimeField()
    class Meta:
        managed = False
        db_table = t("favorites")
        unique_together = (("user","content"),)

class Watchlist(models.Model):
    user = models.ForeignKey(
        CinemaUser, on_delete=models.DO_NOTHING, db_column="user_id", primary_key=True
    )
    content = models.ForeignKey(
        Content, on_delete=models.DO_NOTHING, db_column="content_id"
    )
    created_at = models.DateTimeField()
    class Meta:
        managed = False
        db_table = t("watchlist")
        unique_together = (("user","content"),)

class WatchHistory(models.Model):
    id = models.UUIDField(primary_key=True)
    user = models.ForeignKey(
        CinemaUser, on_delete=models.CASCADE, db_column="user_id"
    )
    content = models.ForeignKey(
        Content, on_delete=models.CASCADE, db_column="content_id"
    )
    episode = models.ForeignKey(
        Episode, null=True, on_delete=models.CASCADE, db_column="episode_id"
    )
    watched_at = models.DateTimeField()
    progress_sec = models.IntegerField()

    class Meta:
        managed = False
        db_table = t("watch_history")
        unique_together = (("user", "content", "episode"),)

class VContentWithRating(models.Model):
    id = models.UUIDField(primary_key=True)
    title = models.TextField()
    type = models.TextField()
    release_year = models.IntegerField()
    avg_rating = models.FloatField(null=True)
    class Meta:
        managed = False
        db_table = t("v_content_with_rating")

class ContentReview(models.Model):
    id = models.UUIDField(primary_key=True)
    user = models.ForeignKey("CinemaUser", on_delete=models.CASCADE, db_column="user_id")
    content = models.ForeignKey("Content", on_delete=models.CASCADE, db_column="content_id")
    rating = models.IntegerField()
    comment = models.TextField(null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = t("content_reviews")
        unique_together = (("user", "content"),)