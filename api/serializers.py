from rest_framework import serializers
from cinemaapp.models import Content, Season

class SeasonSerializer(serializers.ModelSerializer):
    number = serializers.IntegerField(source='season_num', read_only=True)
    display_title = serializers.SerializerMethodField()

    class Meta:
        model = Season
        fields = ("id", "season_num", "number", "display_title")

    def get_display_title(self, obj):
        return obj.title or f"Сезон {obj.season_num}"

class ContentSerializer(serializers.ModelSerializer):
    poster_url = serializers.SerializerMethodField()
    trailer_url = serializers.SerializerMethodField()
    backdrop_url = serializers.SerializerMethodField()
    logo_wide_url = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = ["id", "title", "type", "description", "release_year", "is_free",
                  "poster_url", "trailer_url", "backdrop_url", "logo_wide_url"]

    def get_poster_url(self, obj):
        return obj.cover_image.url if getattr(obj, "cover_image", None) else ""

    def get_trailer_url(self, obj):
        return obj.trailer.url if getattr(obj, "trailer", None) else ""

    def get_backdrop_url(self, obj):
            if getattr(obj, "cover_image_wide", None):
                return obj.cover_image_wide.url
            if getattr(obj, "cover_image", None):
                return obj.cover_image.url
            return ""

    def get_logo_wide_url(self, obj):
            return self.get_backdrop_url(obj)

class RateSerializer(serializers.Serializer):
    value = serializers.IntegerField(min_value=1, max_value=5)

class ProgressGetSerializer(serializers.Serializer):
    position_sec = serializers.IntegerField()
    duration_sec = serializers.IntegerField(allow_null=True)
    is_completed = serializers.BooleanField()

class ProgressPostSerializer(serializers.Serializer):
    sn = serializers.IntegerField(required=False, default=0)
    en = serializers.IntegerField(required=False, default=0)
    position = serializers.IntegerField(min_value=0)
    duration = serializers.IntegerField(required=False, allow_null=True)
    completed = serializers.BooleanField(required=False, default=False)

class PurchaseCreateSerializer(serializers.Serializer):
    content_id = serializers.UUIDField()

class ContentDetailSerializer(ContentSerializer):
    seasons = SeasonSerializer(many=True, source='season', read_only=True)

    class Meta(ContentSerializer.Meta):
        fields = ContentSerializer.Meta.fields + ["seasons"]