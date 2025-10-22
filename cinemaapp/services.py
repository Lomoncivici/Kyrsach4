from .models import Content, MediaAsset, ContentGenre, Genre, VContentWithRating
from django.db.models import Prefetch

def list_content(group="all", limit=20):
    qs = Content.objects.select_related("cover_image","trailer","video")
    if group=="movies": qs = qs.filter(type="movie")
    if group=="series": qs = qs.filter(type="series")
    cs = (ContentGenre.objects.select_related("genre")
          .only("content_id","genre__name"))
    qs = qs.prefetch_related(Prefetch("contentgenre_set", queryset=cs))
    return (qs.order_by("-release_year","title")[:limit])

def get_content(pk):
    qs = (Content.objects.select_related("cover_image","trailer","video")
          .prefetch_related(Prefetch("contentgenre_set",
              queryset=ContentGenre.objects.select_related("genre"))))
    return qs.get(pk=pk)

def rating_map(ids):
    rows = VContentWithRating.objects.filter(id__in=ids).values("id","avg_rating")
    return {r["id"]: r["avg_rating"] for r in rows}