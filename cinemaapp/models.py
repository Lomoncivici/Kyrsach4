from django.db import models

def t(name): return f'cinema"."{name}'

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
    trailer = models.ForeignKey(MediaAsset, null=True, on_delete=models.SET_NULL,
                                db_column="trailer_id", related_name="as_trailer_for")
    video = models.ForeignKey(MediaAsset, null=True, on_delete=models.SET_NULL,
                              db_column="video_id", related_name="as_video_for")
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
    season_num = models.IntegerField()
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

# Вью с рейтингом
class VContentWithRating(models.Model):
    id = models.UUIDField(primary_key=True)
    title = models.TextField()
    type = models.TextField()
    release_year = models.IntegerField()
    avg_rating = models.FloatField(null=True)
    class Meta:
        managed = False
        db_table = t("v_content_with_rating")