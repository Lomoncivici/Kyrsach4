from django.shortcuts import render, get_object_or_404
from uuid import UUID
from cinemaapp import services

def main(request):
    movies = services.list_content("movies", limit=20)
    series = services.list_content("series", limit=20)
    all_items = services.list_content("all", limit=20)
    # подтянем рейтинг
    ratings = services.rating_map([c.id for c in all_items])
    def to_ctx_item(c):
        return {
            "id": c.id,
            "title": c.title,
            "backdrop_url": (c.cover_image.url if c.cover_image else ""),
            "poster_url": (c.cover_image.url if c.cover_image else ""),
            "rating": ratings.get(c.id) or 0.0,
            "can_watch": c.is_free,  # базово; реальная логика — по подписке/покупкам
            "requires_subscription": (not c.is_free and float(c.price or 0) <= 1),
            "year": c.release_year,
            "type": c.type,
            "kind_display": "Фильм" if c.type=="movie" else "Сериал",
            "description": c.description[:180] + "…" if len(c.description)>180 else c.description,
        }
    ctx = {
        "hero_items": [to_ctx_item(x) for x in all_items[:6]],
        "continue_watch": [to_ctx_item(x) for x in all_items[:6]],
        "watchlist": [to_ctx_item(x) for x in all_items[6:12]],
        "anime": [],  # можно фильтровать по жанрам через ContentGenre
        "series": [to_ctx_item(x) for x in series],
        "movies": [to_ctx_item(x) for x in movies],
        "cartoons": [],
    }
    return render(request, "catalog/main.html", ctx)

def content_detail(request, pk: UUID):
    c = get_object_or_404(services.Content, pk=pk)
    genres = [cg.genre.name for cg in c.contentgenre_set.all()]
    rating = services.rating_map([c.id]).get(c.id) or 0.0
    item = {
        "id": c.id, "title": c.title, "type": c.type,
        "poster_url": c.cover_image.url if c.cover_image else "",
        "trailer_url": c.trailer.url if c.trailer else "",
        "video_url": c.video.url if c.type=="movie" and c.video else "",
        "description": c.description, "year": c.release_year,
        "genres": genres, "rating": rating,
        "price": float(c.price or 0), "is_free": c.is_free
    }
    return render(request, "catalog/content_detail.html", {"content": item})