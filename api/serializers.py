from rest_framework import serializers
from cinemaapp.models import Content

class ContentSerializer(serializers.ModelSerializer):
    poster_url = serializers.SerializerMethodField()
    trailer_url = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = ["id", "title", "type", "description", "release_year", "is_free",
                  "poster_url", "trailer_url"]

    def get_poster_url(self, obj):
        return obj.cover_image.url if getattr(obj, "cover_image", None) else ""

    def get_trailer_url(self, obj):
        return obj.trailer.url if getattr(obj, "trailer", None) else ""

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