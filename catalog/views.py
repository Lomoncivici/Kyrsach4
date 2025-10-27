from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.urls import reverse, NoReverseMatch
from django.http import HttpResponse
from uuid import UUID
from cinemaapp import services
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse, Http404, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from cinemaapp.models import ContentGenre, Content, Genre
from django.db.models import Prefetch
import re

# --- утилиты для embed ---
def yt_id(url: str) -> str | None:
  if not url: return None
  m = re.search(r'(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{6,})', url)
  return m.group(1) if m else None

def yt_embed(url: str) -> str | None:
  vid = yt_id(url)
  return f"https://www.youtube.com/embed/{vid}?autoplay=1&playsinline=1&rel=0&modestbranding=1" if vid else None

def rt_id(url: str) -> str | None:
  if not url: return None
  m = re.search(r'rutube\.ru/(?:video|play/embed)/([a-f0-9]{32})', url, re.I)
  return m.group(1) if m else None

def rt_embed(url: str) -> str | None:
  vid = rt_id(url)
  return f"https://rutube.ru/play/embed/{vid}?autoplay=1" if vid else None

@login_required
def account(request):
    return render(request, "/account", {"user": request.user})

def subscribe(request):
    return HttpResponse("Оформление подписки (заглушка)")

def purchase_start(request, pk):
    return HttpResponse(f"Покупка контента {pk} (заглушка)")

def safe_reverse(name, *args, **kwargs) -> str:
    """reverse с безопасным фолбэком на простые URLы."""
    try:
        return reverse(name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        if name == "subscribe":
            return "/subscribe/"
        if name == "purchase_start":
            cid = args[0] if args else kwargs.get("pk") or kwargs.get("id")
            return f"/purchase/{cid}/"
        return "/"

def main(request):
    movies = services.list_content("movies", limit=20)
    series = services.list_content("series", limit=20)
    all_items = services.list_content("all",    limit=20)

    try:
        order = ['-created_at', '-id'] if hasattr(Content, 'created_at') else ['-id']
        hero_qs = (Content.objects
                   .select_related('cover_image', 'cover_image_wide')
                   .prefetch_related('contentgenre_set__genre')
                   .order_by(*order)[:5])
    except Exception:
        hero_qs = all_items[:5]

    if request.user.is_authenticated:
        if hasattr(services, "get_continue_watch_for_user"):
            continue_items = services.get_continue_watch_for_user(request.user, limit=20)
        else:
            continue_items = services.continue_watch_for_user(request.user.username, limit=20)
    else:
        continue_items = []

    if hasattr(services, "build_genre_sections"):
        genre_sections_raw = services.build_genre_sections(limit_per_genre=20)
    else:
        genre_sections_raw = []
        if hasattr(services, "list_genres_non_empty") and hasattr(services, "list_content_by_genre"):
            for g in services.list_genres_non_empty():
                items = services.list_content_by_genre(g, limit=20)
                if items:
                    genre_sections_raw.append({"title": getattr(g, "name", str(g)), "items": items})

    ids_for_ratings = (
        {c.id for c in movies} |
        {c.id for c in series} |
        {c.id for c in all_items} |
        {c.id for c in continue_items} |
        {c.id for s in genre_sections_raw for c in s["items"]}
    )
    ratings = services.rating_map(list(ids_for_ratings)) if ids_for_ratings else {}

    def to_ctx_item(c):
        is_free = bool(c.is_free)
        is_subscription = (not is_free) and (float(getattr(c, "price", 0) or 0) <= 1)
        is_ppv = (not is_free) and (not is_subscription)

        if is_free:
            cta_label = "Смотреть"
            cta_href = safe_reverse("content_detail", c.id)
        elif is_subscription:
            cta_label = "По подписке"
            cta_href = safe_reverse("subscribe")
        else:
            cta_label = "Купить"
            cta_href = safe_reverse("purchase_start", c.id)

        # wide-постер для героя (fallback на обычный)
        def _safe_url(obj):
            return getattr(obj, "url", "") or ""

        backdrop_url = ""
        # 1) предпочитаем широкую обложку
        if hasattr(c, "cover_image_wide") and getattr(c, "cover_image_wide"):
            backdrop_url = _safe_url(c.cover_image_wide)
        # 2) иногда сервис может уже дать backdrop_url строкой
        elif hasattr(c, "backdrop_url") and getattr(c, "backdrop_url"):
            backdrop_url = c.backdrop_url
        # 3) fallback на обычную обложку
        elif getattr(c, "cover_image", None):
            backdrop_url = _safe_url(c.cover_image)

        desc_full = (getattr(c, "description", "") or "").strip()
        words = desc_full.split()
        desc_long = len(words) > 25
        desc_short = " ".join(words[:25]) + ("…" if desc_long else "")

        genres = []
        if hasattr(c, "contentgenre_set"):
            for cg in c.contentgenre_set.all():
                g = getattr(cg, "genre", None)
                if g and getattr(g, "name", None):
                    genres.append(g.name)

        return {
            "id": c.id,
            "title": c.title,
            "backdrop_url": backdrop_url,
            "poster_url":   (_safe_url(c.cover_image) if getattr(c, "cover_image", None) else ""),
            "rating": float(ratings.get(c.id) or 0.0),
            "year": c.release_year,
            "type": c.type,
            "kind_display": ("Фильм" if c.type == "movie" else "Сериал"),
            "description": (c.description[:180] + "…") if len(c.description) > 180 else c.description,

            "is_free": is_free,
            "is_subscription": is_subscription,
            "is_ppv": is_ppv,
            "cta_label": cta_label,
            "cta_href": cta_href,

            "desc_full": desc_full,
            "desc_short": desc_short,
            "desc_long": desc_long,
            "genres": genres,
        }
    
    hero_items = [to_ctx_item(c) for c in hero_qs]

    genre_sections_vm = []
    for s in genre_sections_raw:
        items_vm = [to_ctx_item(x) for x in s["items"]]
        if items_vm:
            genre_sections_vm.append({"title": s["title"], "items": items_vm})

    ctx = {
        "series":         [to_ctx_item(x) for x in series],
        "movies":         [to_ctx_item(x) for x in movies],

        "hero_items": hero_items,
        "continue_watch":  [to_ctx_item(x) for x in continue_items],

        "genre_sections": genre_sections_vm
    }
    return render(request, "catalog/main.html", ctx)

def content_detail(request, pk):
    c = (Content.objects
         .select_related('cover_image_wide', 'cover_image', 'trailer', 'video')
         .prefetch_related(
                   Prefetch('contentgenre_set', queryset=ContentGenre.objects.select_related('genre'))
               )
         .get(pk=pk))
    
    genres = [cg.genre.name for cg in c.contentgenre_set.all()]

    backdrop = (c.cover_image_wide.url if getattr(c, 'cover_image_wide', None) else
                (c.cover_image.url if getattr(c, 'cover_image', None) else ""))

    # доступ: можно смотреть прямо сейчас?
    can_watch = services.can_watch(request.user, c) if request.user.is_authenticated else bool(c.is_free)

    # режим доступа: free / subscription / ppv
    is_free = bool(c.is_free)
    price = float(getattr(c, "price", 0) or 0)
    access_mode = "free" if is_free else ("subscription" if price <= 1 else "ppv")

    # универсальный CTA — показываем ТОЛЬКО если смотреть нельзя
    cta_label = ""
    cta_url = ""
    if not can_watch and not is_free:
        if access_mode == "subscription":
            cta_label = "По подписке"
            cta_url = safe_reverse("subscribe")
        else:
            cta_label = "Купить"
            cta_url = safe_reverse("purchase_start", c.id)

    rating = services.rating_for(c.id)

    item = {
        "id": c.id,
        "title": c.title,
        "type": c.type,
        "backdrop_url": backdrop,
        "poster_url":  c.cover_image.url if c.cover_image else "",
        "trailer_url": c.trailer.url if c.trailer else "",
        # для фильма отдаём реальный src только при доступе (JS сам встраивает плеер: YouTube/RuTube/<video>)
        "video_url":   (c.video.url if c.type == "movie" and c.video and can_watch else ""),
        "description": c.description,
        "year": c.release_year,
        "genres": [cg.genre.name for cg in c.contentgenre_set.all()],
        "rating": rating,
        "is_free": is_free,
        "can_watch": bool(can_watch),
        "access_mode": access_mode,   # нужно шаблону/JS для отрисовки CTA
        "cta_label": cta_label,
        "cta_url": cta_url,
    }

    seasons = services.series_tree(c) if c.type == "series" else []
    norm_seasons = []
    for i, s in enumerate(seasons or [], start=1):
        sn = s.get('season_num') or s.get('season') or s.get('number') or s.get('index') or i
        eps = []
        for j, e in enumerate(s.get('episodes') or [], start=1):
            en = e.get('episode_num') or e.get('number') or e.get('episode') or e.get('index') or j
            eps.append({
                'episode_num': en,
                'title': e.get('title') or e.get('name') or '',
                'video_url': e.get('video_url') or ''
            })
        norm_seasons.append({'season_num': int(sn), 'episodes': eps})
    seasons = norm_seasons
    
    # скрываем реальные URL эпизодов, если нет доступа
    if not can_watch:
        for s in seasons:
            for e in s["episodes"]:
                e["video_url"] = ""

    return render(request, "catalog/content_detail.html", {
        "content": item,
        "seasons": seasons,
        'genres': genres,
    })

# --- API источников для плеера ---
@login_required
def movie_source(request, pk):
  c = get_object_or_404(Content.objects.select_related("video"), pk=pk, type="movie")
  if not c.video: raise Http404()
  if not c.is_free and not services.can_watch(request.user, c): return HttpResponseForbidden("no access")
  url = c.video.url or ""
  u = url.lower()
  if "youtu" in u:
    em = yt_embed(url);  return JsonResponse({"url": em, "kind": "youtube"}) if em else (_ for _ in ()).throw(Http404())
  if "rutube" in u:
    em = rt_embed(url);  return JsonResponse({"url": em, "kind": "rutube"}) if em else (_ for _ in ()).throw(Http404())
  return JsonResponse({"url": url, "kind": "file"})

@login_required
def episode_source(request, pk, sn, en):
  from cinemaapp.models import Episode
  c = get_object_or_404(Content, pk=pk, type="series")
  if not c.is_free and not services.can_watch(request.user, c): return HttpResponseForbidden("no access")
  try:
    ep = (Episode.objects.select_related("video","season")
          .get(season__content=c, season__season_num=sn, episode_num=en))
  except Episode.DoesNotExist:
    raise Http404()
  if not ep.video: raise Http404()
  url = ep.video.url or ""
  u = url.lower()
  if "youtu" in u:
    em = yt_embed(url);  return JsonResponse({"url": em, "kind": "youtube"}) if em else (_ for _ in ()).throw(Http404())
  if "rutube" in u:
    em = rt_embed(url);  return JsonResponse({"url": em, "kind": "rutube"}) if em else (_ for _ in ()).throw(Http404())
  return JsonResponse({"url": url, "kind": "file"})

# --- рейтинг ---
@login_required
@require_POST
def rate_content(request, pk):
    """
    POST /content/<uuid:pk>/rate/   body: value=1..10
    Возвращает новое среднее: {"ok": true, "avg": "7.5"}
    """
    try:
        value = int(request.POST.get("value", "0"))
    except ValueError:
        return HttpResponseBadRequest("invalid rating")
    if not (1 <= value <= 10):
        return HttpResponseBadRequest("rating must be from 1 to 10")

    # Проверяем существование контента, чтобы вернуть 404, а не 500
    _ = get_object_or_404(Content, pk=pk)
    try:
        avg = services.rate_content(pk, value)
    except PermissionError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=401)
    return JsonResponse({"ok": True, "avg": str(avg)})

@login_required
@require_POST
def watchlist_toggle(request, pk):
    """
    POST /content/<uuid:pk>/watchlist-toggle/
    Возвращает {"in_watchlist": true|false} — БЕЗ лишнего вложения.
    """
    _ = get_object_or_404(Content, pk=pk)
    try:
        in_list = services.watchlist_toggle(pk)
    except PermissionError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=401)
    return JsonResponse({"in_watchlist": bool(in_list)})

@login_required
def my_page(request):
    purchases = services.list_user_purchases(request.user)
    ratings   = services.list_user_ratings(request.user)
    history   = services.list_user_history(request.user)
    favorites = services.list_user_favorites(request.user)

    # Один запрос к ORM для карточек контента
    ids = {str(x['content_id']) for x in (purchases + ratings + history + favorites)}
    items = {str(c.id): c for c in Content.objects.filter(id__in=ids).select_related('cover_image')}

    def pack(row, extra: dict):
        c = items.get(str(row['content_id']))
        return {
            'id': str(row['content_id']),
            'title': c.title if c else '—',
            'poster_url': c.cover_image.url if c and c.cover_image else '',
            'url': reverse('catalog:content_detail', args=[c.id]) if c else '#',
            **extra
        }

    purchases_vm = [pack(r, {'when': r['purchased_at']}) for r in purchases]
    ratings_vm   = [pack(r, {'rating': r['rating'], 'when': r['updated_at']}) for r in ratings]
    history_vm   = [pack(r, {'when': r['viewed_at']}) for r in history]
    favorites_vm = [pack(r, {'when': r['created_at']}) for r in favorites]

    return render(request, 'catalog/my.html', {
        'purchases': purchases_vm,
        'ratings': ratings_vm,
        'history': history_vm,
        'favorites': favorites_vm,
    })