import uuid
from venv import logger
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse, NoReverseMatch
from django.http import HttpResponse
from uuid import UUID
from catalog.utils.bank_service import BankService
from cinemaapp import services
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse, Http404, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from cinemaapp.models import ContentGenre, Content, Genre
from django.db.models import Prefetch
from cinemaapp.models import Content
from django.contrib import messages
from django.db.models import Q
from datetime import timedelta
from .models import SubscriptionPlan, UserSubscription, Purchase, CinemaUser, Payment
from cinemaapp.models import Content
from cinemaapp import services
import re

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

def safe_reverse(name, *args, **kwargs) -> str:
    """reverse с безопасным фолбэком на простые URLы."""
    try:
        return reverse(name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        if name == "subscribe":
            return "/subscribe/"
        if name == "purchase_start":
            cid = args[0] if args else kwargs.get("pk") or kwargs.get("id")
            return f"/purchase/{cid}/start/"
        return "/"

def main(request):

    movies = services.list_content("movies", limit=20)
    series = services.list_content("series", limit=20)
    all_items = services.list_content("all", limit=20)

    try:
        hero_qs = list(all_items[:5])
    except Exception:
        hero_qs = []

    if request.user.is_authenticated:
        if hasattr(services, "get_continue_watch_for_user"):
            continue_items = services.get_continue_watch_for_user(request.user, limit=20)
        else:
            continue_items = []
    else:
        continue_items = []


    if continue_items and hasattr(services, 'load_content_with_media'):
        continue_items = services.load_content_with_media(continue_items)
    elif continue_items and hasattr(services, '_load_media_for_content'):
        continue_items = services._load_media_for_content(continue_items)

    genre_sections_raw = []
    if hasattr(services, "build_genre_sections"):
        try:
            genre_sections_raw = services.build_genre_sections(limit_per_genre=20)
        except Exception as e:
            print(f"Error in build_genre_sections: {e}")

            if movies:
                genre_sections_raw.append({"title": "Фильмы", "items": movies[:10]})
            if series:
                genre_sections_raw.append({"title": "Сериалы", "items": series[:10]})
    else:

        if movies:
            genre_sections_raw.append({"title": "Фильмы", "items": movies[:10]})
        if series:
            genre_sections_raw.append({"title": "Сериалы", "items": series[:10]})

    if genre_sections_raw:

        all_genre_content = []
        for section in genre_sections_raw:
            all_genre_content.extend(section.get("items", []))
        

        if hasattr(services, 'load_content_with_media'):
            all_genre_content = services.load_content_with_media(all_genre_content)
        elif hasattr(services, '_load_media_for_content'):
            all_genre_content = services._load_media_for_content(all_genre_content)
        

        idx = 0
        for section in genre_sections_raw:
            items = section.get("items", [])
            if items:

                section["items"] = all_genre_content[idx:idx + len(items)]
                idx += len(items)

    from django.db import connection

    all_content_ids = []
    for lst in [movies, series, hero_qs, continue_items]:
        if lst:
            for c in lst:
                if hasattr(c, 'id'):
                    all_content_ids.append(c.id)

    for section in genre_sections_raw:
        for item in section.get("items", []):
            if hasattr(item, 'id'):
                all_content_ids.append(item.id)

    content_genres = {}
    if all_content_ids:
        id_strs = [str(id) for id in all_content_ids]
        with connection.cursor() as cur:
            cur.execute("""
                SELECT cg.content_id, g.name
                FROM cinema.content_genres cg
                JOIN cinema.genres g ON g.id = cg.genre_id
                WHERE cg.content_id = ANY(%s)
                ORDER BY g.name
            """, [id_strs])
            for content_id, genre_name in cur.fetchall():
                content_genres.setdefault(str(content_id), []).append(genre_name)

    ratings = {}
    if all_content_ids:
        ratings = services.rating_map(all_content_ids)

    def to_ctx_item(c):
        is_free = bool(getattr(c, "is_free", False))
        price = float(getattr(c, "price", 0) or 0)
        is_subscription = (not is_free) and (price <= 1)
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


        backdrop_url = ""
        poster_url = ""
        

        if hasattr(c, "cover_image") and c.cover_image:
            if hasattr(c.cover_image, 'url'):
                poster_url = c.cover_image.url
            elif hasattr(c.cover_image, 'id'):

                poster_url = services._get_media_url(c.cover_image.id) if hasattr(services, '_get_media_url') else ""
            else:

                try:
                    poster_url = getattr(c.cover_image, 'image_url', '')
                except:
                    pass

        if hasattr(c, "cover_image_wide") and c.cover_image_wide:
            if hasattr(c.cover_image_wide, 'url'):
                backdrop_url = c.cover_image_wide.url
            elif hasattr(c.cover_image_wide, 'id'):
                backdrop_url = services._get_media_url(c.cover_image_wide.id) if hasattr(services, '_get_media_url') else ""
            else:

                try:
                    backdrop_url = getattr(c.cover_image_wide, 'image_url', '')
                except:
                    pass

        if not backdrop_url and poster_url:
            backdrop_url = poster_url

        desc_full = (getattr(c, "description", "") or "").strip()
        words = desc_full.split()
        desc_long = len(words) > 25
        desc_short = " ".join(words[:25]) + ("…" if desc_long else "")


        genres = content_genres.get(str(c.id), [])

        return {
            "id": c.id,
            "title": getattr(c, "title", ""),
            "backdrop_url": backdrop_url,
            "poster_url": poster_url,
            "rating": float(ratings.get(c.id) or 0.0),
            "year": getattr(c, "release_year", 0),
            "type": getattr(c, "type", "movie"),
            "kind_display": ("Фильм" if getattr(c, "type", "") == "movie" else "Сериал"),
            "description": (desc_full[:180] + "…") if len(desc_full) > 180 else desc_full,

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


    continue_watch_vm = [to_ctx_item(c) for c in continue_items]

    genre_sections_vm = []
    for section in genre_sections_raw:
        items_vm = [to_ctx_item(item) for item in section.get("items", [])]
        if items_vm:
            genre_sections_vm.append({
                "title": section.get("title", "Жанр"),
                "items": items_vm
            })

    ctx = {

        "series": [to_ctx_item(x) for x in series[:10]],
        "movies": [to_ctx_item(x) for x in movies[:10]],
        "hero_items": hero_items,
        "continue_watch": continue_watch_vm,

        "genre_sections": genre_sections_vm
    }
    return render(request, "catalog/main.html", ctx)

def content_detail(request, pk):
    from django.db import connection
    

    c = services.get_content(pk)
    

    genres = []
    with connection.cursor() as cur:
        cur.execute("""
            SELECT g.name
            FROM cinema.content_genres cg
            JOIN cinema.genres g ON g.id = cg.genre_id
            WHERE cg.content_id = %s
            ORDER BY g.name
        """, [str(pk)])
        genres = [row[0] for row in cur.fetchall()]

    backdrop = ""
    poster_url = ""
    

    if hasattr(c, "cover_image_wide") and c.cover_image_wide:

        if hasattr(c.cover_image_wide, 'url') and c.cover_image_wide.url:
            backdrop = c.cover_image_wide.url

        elif hasattr(c.cover_image_wide, 'id'):
            image_id = str(c.cover_image_wide.id)
            with connection.cursor() as cur:
                cur.execute("SELECT url FROM cinema.media_assets WHERE id = %s", [image_id])
                row = cur.fetchone()
                if row and row[0]:
                    backdrop = row[0]

        elif isinstance(c.cover_image_wide, str) and len(c.cover_image_wide) == 36:
            with connection.cursor() as cur:
                cur.execute("SELECT url FROM cinema.media_assets WHERE id = %s", [c.cover_image_wide])
                row = cur.fetchone()
                if row and row[0]:
                    backdrop = row[0]

        else:
            try:

                if isinstance(c.cover_image_wide, str) and c.cover_image_wide.startswith('http'):
                    backdrop = c.cover_image_wide

                elif hasattr(c.cover_image_wide, 'image_url'):
                    backdrop = c.cover_image_wide.image_url
            except:
                pass
    

    if not backdrop and hasattr(c, "cover_image") and c.cover_image:

        if hasattr(c.cover_image, 'url') and c.cover_image.url:
            backdrop = c.cover_image.url
            poster_url = c.cover_image.url

        elif hasattr(c.cover_image, 'id'):
            image_id = str(c.cover_image.id)
            with connection.cursor() as cur:
                cur.execute("SELECT url FROM cinema.media_assets WHERE id = %s", [image_id])
                row = cur.fetchone()
                if row and row[0]:
                    backdrop = row[0]
                    poster_url = row[0]

        elif isinstance(c.cover_image, str) and len(c.cover_image) == 36:
            with connection.cursor() as cur:
                cur.execute("SELECT url FROM cinema.media_assets WHERE id = %s", [c.cover_image])
                row = cur.fetchone()
                if row and row[0]:
                    backdrop = row[0]
                    poster_url = row[0]

        else:
            try:
                if isinstance(c.cover_image, str) and c.cover_image.startswith('http'):
                    backdrop = c.cover_image
                    poster_url = c.cover_image
                elif hasattr(c.cover_image, 'image_url'):
                    backdrop = c.cover_image.image_url
                    poster_url = c.cover_image.image_url
            except:
                pass

    can_watch = services.can_watch(request.user, c) if request.user.is_authenticated else bool(c.is_free)


    is_free = bool(c.is_free)
    price = float(getattr(c, "price", 0) or 0)
    access_mode = "free" if is_free else ("subscription" if price <= 1 else "ppv")


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
        "poster_url": poster_url,
        "trailer_url": "",
        "video_url": "",
        "description": c.description,
        "year": c.release_year,
        "genres": genres,
        "rating": rating,
        "is_free": is_free,
        "can_watch": bool(can_watch),
        "access_mode": access_mode,
        "cta_label": cta_label,
        "cta_url": cta_url,
    }


    if not item["poster_url"] and hasattr(c, "cover_image") and c.cover_image:
        if hasattr(c.cover_image, 'url') and c.cover_image.url:
            item["poster_url"] = c.cover_image.url
        elif hasattr(c.cover_image, 'id'):
            image_id = str(c.cover_image.id)
            with connection.cursor() as cur:
                cur.execute("SELECT url FROM cinema.media_assets WHERE id = %s", [image_id])
                row = cur.fetchone()
                if row and row[0]:
                    item["poster_url"] = row[0]

    seasons = services.series_tree(c) if c.type == "series" else []

    if not can_watch:
        for s in seasons:
            for e in s.get("episodes", []):
                if "video_url" in e:
                    e["video_url"] = ""

    return render(request, "catalog/content_detail.html", {
        "content": item,
        "seasons": seasons,
        'genres': genres,
    })


@login_required
def movie_source(request, pk):
    c = get_object_or_404(Content.objects.select_related("video"), pk=pk, type="movie")
    if not c.video: raise Http404()
    if not c.is_free and not services.can_watch(request.user, c): 
        return HttpResponseForbidden("no access")
    
    url = c.video.url or ""
    u = url.lower()
    
    if "youtu" in u:
        em = yt_embed(url);  
        return JsonResponse({"url": em, "kind": "youtube"}) if em else (_ for _ in ()).throw(Http404())
    
    if "rutube" in u:

        from cinemaapp.services import get_rutube_video_url
        direct_url = get_rutube_video_url(url)
        
        if direct_url:

            return JsonResponse({
                "url": direct_url, 
                "kind": "file",
                "source": "rutube"
            })
        else:

            return JsonResponse({
                "url": "", 
                "kind": "rutube_external",
                "direct_url": url,
                "message": "Открыть на Rutube"
            })
    
    return JsonResponse({"url": url, "kind": "file"})

def extract_rutube_id(url):
    """Извлечь ID видео из URL Rutube"""
    import re
    
    patterns = [
        r'rutube\.ru/video/([a-f0-9]{32})',
        r'rutube\.ru/play/embed/([a-f0-9]{32})',
        r'rutube\.ru/video/([a-zA-Z0-9_-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None

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

@login_required
def subscriptions_view(request):
    """Страница подписок и покупок контента"""

    try:
        cinema_user = CinemaUser.objects.get(login=request.user.username)
        user_found = True
    except CinemaUser.DoesNotExist:
        messages.error(request, "Пользователь не найден в системе")
        cinema_user = None
        user_found = False
    

    active_sub = None
    if cinema_user:

        active_sub = UserSubscription.get_current_active_subscription(cinema_user)

    all_subs = []
    if cinema_user:
        all_subs_query = UserSubscription.objects.filter(
            user=cinema_user
        ).select_related('plan').order_by('-started_at')

        all_subs = [
            sub for sub in all_subs_query 
            if not (sub.plan.code.lower() == 'admin' or 'админ' in sub.plan.name.lower())
        ]

    
    total_count = 0
    active_count = 0
    cancelled_count = 0
    expired_count = 0
    
    if cinema_user:

        total_count = UserSubscription.objects.filter(user=cinema_user).count()

        now = timezone.now()
        active_count = UserSubscription.objects.filter(
            user=cinema_user,
            status='active',
            started_at__lte=now,
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).count()

        future_count = UserSubscription.objects.filter(
            user=cinema_user,
            status='active',
            started_at__gt=now
        ).count()
        

        cancelled_count = UserSubscription.objects.filter(
            user=cinema_user,
            status='cancelled'
        ).count()

        expired_count = UserSubscription.objects.filter(
            user=cinema_user,
            status='active',
            expires_at__lt=now,
            started_at__lte=now
        ).count()


        expired_count += UserSubscription.objects.filter(
            user=cinema_user,
            status='expired'
        ).count()

    all_plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
    
    plans = [
        plan for plan in all_plans 
        if not (plan.code.lower() == 'admin' or 'админ' in plan.name.lower())
    ]

    query = request.GET.get('q', '').strip()
    

    purchased_content_ids = []
    if cinema_user:
        purchased_content_ids = list(Purchase.objects.filter(
            user=cinema_user
        ).values_list('content_id', flat=True))
    

    content_qs = Content.objects.filter(
        is_free=False,
        price__gte=1
    )


    if purchased_content_ids:
        content_qs = content_qs.exclude(id__in=purchased_content_ids)
    

    if query:
        content_qs = content_qs.filter(
            Q(title__icontains=query) | 
            Q(description__icontains=query)
        )
    

    content_list = content_qs.distinct()[:20]

    total_spent_on_subscriptions = 0
    if cinema_user:
        from django.db.models import Sum
        total_spent_result = UserSubscription.objects.filter(
            user=cinema_user
        ).aggregate(total=Sum('plan__price'))
        
        total_spent_on_subscriptions = total_spent_result['total'] or 0

    total_spent_on_content = 0
    if cinema_user:
        total_spent_result = Purchase.objects.filter(
            user=cinema_user
        ).aggregate(total=Sum('content__price'))
        
        total_spent_on_content = total_spent_result['total'] or 0
    
    context = {
        'subscription': active_sub,
        'subscriptions': all_subs,
        'plans': plans,
        'content_list': content_list,
        'query': query,
        'cinema_user': cinema_user,
        

        'total_count': total_count,
        'active_count': active_count,
        'cancelled_count': cancelled_count,
        'expired_count': expired_count,
        'total_spent_on_subscriptions': total_spent_on_subscriptions,
        'total_spent_on_content': total_spent_on_content,

        'purchased_content_ids': purchased_content_ids,
    }
    
    return render(request, 'catalog/subscriptions.html', context)

@login_required
def purchase_start(request, pk):
    """Начало процесса покупки контента - страница подтверждения"""
    content = get_object_or_404(Content, pk=pk)
    

    if content.is_free or content.price < 1:
        messages.info(request, "Этот контент нельзя купить отдельно")
        return redirect('catalog:content_detail', pk=pk)

    try:
        cinema_user = CinemaUser.objects.get(login=request.user.username)
        if Purchase.objects.filter(user=cinema_user, content=content).exists():
            messages.warning(request, "Вы уже купили этот контент")
            return redirect('catalog:content_detail', pk=pk)
    except CinemaUser.DoesNotExist:
        messages.error(request, "Пользователь не найден")
        return redirect('catalog:content_detail', pk=pk)
    

    try:
        cinema_user = CinemaUser.objects.get(login=request.user.username)
        active_subs = UserSubscription.get_active_subscriptions(cinema_user)
        now = timezone.now()
        has_active_sub = active_subs.filter(
            started_at__lte=now,
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gte=now)
        ).exists()
        

        if not content.is_free and 0.01 <= content.price <= 0.99 and has_active_sub:
            messages.info(request, "Этот контент доступен вам по подписке")
            return redirect('catalog:content_detail', pk=pk)
    except CinemaUser.DoesNotExist:
        pass

    return render(request, 'catalog/purchase_confirm.html', {
        'content': content
    })

@login_required
@require_POST
def purchase_content(request, pk):
    """Обработка покупки контента с фиктивной оплатой"""
    content = get_object_or_404(Content, pk=pk)

    if content.is_free or content.price < 1:
        messages.error(request, "Этот контент нельзя купить отдельно")
        return redirect('catalog:content_detail', pk=pk)

    card_number = request.POST.get('card_number', '').replace(' ', '')
    expiry_date = request.POST.get('expiry_date', '')
    cvc = request.POST.get('cvc', '')

    try:
        cinema_user = CinemaUser.objects.get(login=request.user.username)
        if Purchase.objects.filter(user=cinema_user, content=content).exists():
            messages.warning(request, "Вы уже купили этот контент")
            return redirect('catalog:content_detail', pk=pk)
    except CinemaUser.DoesNotExist:
        messages.error(request, "Пользователь не найден в системе")
        return redirect('catalog:content_detail', pk=pk)

    if card_number:
        if not (len(card_number) == 16 and card_number.isdigit()):
            messages.error(request, "Неверный номер карты")
            return redirect('catalog:purchase_start', pk=pk)
        
        if not (len(cvc) == 3 and cvc.isdigit()):
            messages.error(request, "Неверный CVC код")
            return redirect('catalog:purchase_start', pk=pk)
    
    Purchase.objects.create(
        id=uuid.uuid4(),
        user=cinema_user,
        content=content,
        purchased_at=timezone.now()
    )
    
    from .models import Payment
    Payment.objects.create(
        txn_uuid=uuid.uuid4(),
        amount=content.price,
        status='paid',
        paid_at=timezone.now(),
        purchase=Purchase.objects.filter(user=cinema_user, content=content).first(),
        created_at=timezone.now()
    )
    
    messages.success(request, f"Контент '{content.title}' успешно куплен!")
    return redirect('catalog:content_detail', pk=pk)

@login_required
def activate_subscription(request, plan_code):
    """Страница подтверждения покупки подписки"""
    plan = get_object_or_404(SubscriptionPlan, code=plan_code, is_active=True)

    try:
        cinema_user = CinemaUser.objects.get(login=request.user.username)
    except CinemaUser.DoesNotExist:
        messages.error(request, "Пользователь не найден")
        return redirect('catalog:subscribe')
    

    current_active_sub = None
    current_subscription = None
    

    active_subs = UserSubscription.get_active_subscriptions(cinema_user).select_related('plan').order_by('-expires_at')
    
    if active_subs.exists():
        current_active_sub = active_subs.first()
        current_subscription = current_active_sub
    

    new_subscription_start = timezone.now()
    will_extend_current = False
    
    if current_active_sub:

        new_subscription_start = current_active_sub.expires_at
        will_extend_current = True

    new_subscription_expiry = new_subscription_start + timedelta(days=plan.period_months * 30)
    
    return render(request, 'catalog/subscription_confirm.html', {
        'plan': plan,
        'current_subscription': current_subscription,
        'new_subscription_start': new_subscription_start,
        'new_subscription_expiry': new_subscription_expiry,
        'will_extend_current': will_extend_current,
        'cinema_user': cinema_user,
    })


def luhn_check(card_number):
    """Проверка номера карты алгоритмом Луна"""

    card_number = card_number.replace(' ', '')

    if not card_number.isdigit():
        return False
    

    total = 0
    reverse_digits = card_number[::-1]
    
    for i, digit in enumerate(reverse_digits):
        n = int(digit)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    
    return total % 10 == 0

@login_required
@require_POST
def process_payment(request, pk):
    """Обработка РЕАЛЬНОГО платежа через банковский сервис"""
    content = get_object_or_404(Content, pk=pk)
    

    card_number = request.POST.get('card_number', '').replace(' ', '')
    expiry_date = request.POST.get('expiry_date', '')
    cvc = request.POST.get('cvc', '')
    cardholder_name = request.POST.get('cardholder_name', '')
    form_email = request.POST.get('email', '')

    if not BankService.health_check():
        messages.error(request, "Платежный сервис временно недоступен. Попробуйте позже.")
        return redirect('catalog:purchase_start', pk=pk)

    errors = []
    
    if not card_number or len(card_number.replace(' ', '')) != 16:
        errors.append("Номер карты должен содержать 16 цифр")
    
    if not expiry_date or '/' not in expiry_date:
        errors.append("Введите срок действия в формате ММ/ГГ")
    else:
        try:
            month_str, year_str = expiry_date.split('/')
            expiry_month = int(month_str.strip())
            expiry_year = int(year_str.strip())
            
            if not (1 <= expiry_month <= 12):
                errors.append("Месяц должен быть от 01 до 12")
            
            if not (23 <= expiry_year <= 40) and not (2023 <= expiry_year <= 2040):
                errors.append("Некорректный год")
        except ValueError:
            errors.append("Неверный формат даты")
    
    if not cvc or len(cvc) != 3 or not cvc.isdigit():
        errors.append("CVC код должен содержать 3 цифры")
    
    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect('catalog:purchase_start', pk=pk)
    

    try:
        cinema_user = CinemaUser.objects.get(login=request.user.username)
    except CinemaUser.DoesNotExist:
        messages.error(request, "Пользователь не найден")
        return redirect('catalog:content_detail', pk=pk)
    

    if Purchase.objects.filter(user=cinema_user, content=content).exists():
        messages.warning(request, "Вы уже купили этот контент")
        return redirect('catalog:content_detail', pk=pk)
    

    if form_email and form_email != cinema_user.email:
        cinema_user.email = form_email
        cinema_user.save()
        messages.info(request, "Email обновлен")
    

    month_str, year_str = expiry_date.split('/')
    expiry_month = int(month_str.strip())
    expiry_year = int(year_str.strip())
    

    if expiry_year < 100:
        expiry_year_full = 2000 + expiry_year
    else:
        expiry_year_full = expiry_year
    
    card_check_data = {
        'card_number': card_number,
        'expiry_month': expiry_month,
        'expiry_year': expiry_year,
        'cvc': cvc
    }
    

    check_result = BankService.check_card(card_check_data)
    
    if not check_result.get('success'):
        error_msg = check_result.get('error', 'Карта недействительна')
        messages.error(request, f"Ошибка проверки карты: {error_msg}")
        

        if 'hint' in check_result:
            messages.info(request, f"Подсказка: {check_result['hint']}")
        
        return redirect('catalog:purchase_start', pk=pk)
    

    payment_data = {
        'card_number': card_number,
        'expiry_month': expiry_month,
        'expiry_year': expiry_year,
        'cvc': cvc,
        'amount': float(content.price)
    }
    
    payment_result = BankService.process_payment(payment_data)
    
    if not payment_result.get('success'):
        error_msg = payment_result.get('error', 'Ошибка оплаты')
        messages.error(request, f"Оплата не прошла: {error_msg}")

        if 'hint' in payment_result:
            messages.info(request, f"Подсказка: {payment_result['hint']}")
        
        return redirect('catalog:purchase_start', pk=pk)
    

    purchase = Purchase.objects.create(
        id=uuid.uuid4(),
        user=cinema_user,
        content=content,
        purchased_at=timezone.now()
    )
    

    transaction_id = payment_result.get('transaction_id', f'TXN{uuid.uuid4().hex[:8].upper()}')
    auth_code = payment_result.get('auth_code', '000000')
    
    payment = Payment.objects.create(
        id=uuid.uuid4(),
        txn_uuid=transaction_id,
        amount=content.price,
        status='paid',
        paid_at=timezone.now(),
        purchase=purchase,
        created_at=timezone.now()
    )
    

    try:
        from .utils.email_sender import send_combined_email
        send_combined_email(cinema_user, payment, purchase=purchase)
        
        messages.success(request, 
            f"Оплата прошла успешно! ✅"
            f"Контент '{content.title}' добавлен в вашу библиотеку."
            f"Код авторизации: {auth_code}"
            f"ID транзакции: {transaction_id}"
            f"Подтверждение отправлено на {cinema_user.email}")
            
    except Exception as e:

        messages.success(request, 
            f"Оплата прошла успешно! ✅"
            f"Контент '{content.title}' добавлен в вашу библиотеку."
            f"Код авторизации: {auth_code}"
            f"ID транзакции: {transaction_id}")
    

    print(f"[PAYMENT] Успешная покупка: user={cinema_user.login}, content={content.title}, "
          f"amount={content.price}, transaction={transaction_id}")
    
    return redirect('catalog:content_detail', pk=pk)

@login_required
@require_POST
def process_subscription_payment(request, plan_code):
    """Обработка фиктивного платежа за подписку"""
    plan = get_object_or_404(SubscriptionPlan, code=plan_code, is_active=True)
    

    if not BankService.health_check():
        messages.error(request, "Платежный сервис временно недоступен. Попробуйте позже.")
        return redirect('catalog:activate_subscription', plan_code=plan_code)
    

    card_number = request.POST.get('card_number', '').replace(' ', '')
    expiry_date = request.POST.get('expiry_date', '')
    cvc = request.POST.get('cvc', '')
    cardholder_name = request.POST.get('cardholder_name', '')
    form_email = request.POST.get('email', '')
    extend_after_current = request.POST.get('extend_after_current', 'false')


    if not BankService.health_check():
        messages.error(request, "Платежный сервис временно недоступен. Попробуйте позже.")
        return redirect('catalog:activate_subscription', plan_code=plan_code)
    

    errors = []
    
    if not card_number or len(card_number.replace(' ', '')) != 16:
        errors.append("Номер карты должен содержать 16 цифр")
    
    if not expiry_date or '/' not in expiry_date:
        errors.append("Введите срок действия в формате ММ/ГГ")
    else:
        try:
            month_str, year_str = expiry_date.split('/')
            expiry_month = int(month_str.strip())
            expiry_year = int(year_str.strip())
            
            if not (1 <= expiry_month <= 12):
                errors.append("Месяц должен быть от 01 до 12")
            
            if not (23 <= expiry_year <= 40) and not (2023 <= expiry_year <= 2040):
                errors.append("Некорректный год")
        except ValueError:
            errors.append("Неверный формат даты")
    
    if not cvc or len(cvc) != 3 or not cvc.isdigit():
        errors.append("CVC код должен содержать 3 цифры")
    
    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect('catalog:activate_subscription', plan_code=plan_code)
    

    if not card_number or len(card_number.replace(' ', '')) < 16:
        messages.error(request, "Введите номер карты")
        return redirect('catalog:activate_subscription', plan_code=plan_code)
    
    if not expiry_date or len(expiry_date) != 5:
        messages.error(request, "Введите срок действия карты")
        return redirect('catalog:activate_subscription', plan_code=plan_code)
    
    if not cvc or len(cvc) != 3:
        messages.error(request, "Введите CVC код")
        return redirect('catalog:activate_subscription', plan_code=plan_code)
 
    try:
        cinema_user = CinemaUser.objects.get(login=request.user.username)
    except CinemaUser.DoesNotExist:
        messages.error(request, "Пользователь не найден")
        return redirect('catalog:subscribe')

    month_str, year_str = expiry_date.split('/')
    expiry_month = int(month_str.strip())
    expiry_year = int(year_str.strip())
    
    card_check_data = {
        'card_number': card_number,
        'expiry_month': expiry_month,
        'expiry_year': expiry_year,
        'cvc': cvc
    }
    
    check_result = BankService.check_card(card_check_data)
    
    if not check_result.get('success'):
        error_msg = check_result.get('error', 'Карта недействительна')
        messages.error(request, f"Ошибка проверки карты: {error_msg}")
        return redirect('catalog:activate_subscription', plan_code=plan_code)

    payment_data = {
        'card_number': card_number,
        'expiry_month': expiry_month,
        'expiry_year': expiry_year,
        'cvc': cvc,
        'amount': float(plan.price)
    }
    
    payment_result = BankService.process_payment(payment_data)
    
    if not payment_result.get('success'):
        error_msg = payment_result.get('error', 'Ошибка оплаты')
        messages.error(request, f"Оплата не прошла: {error_msg}")
        return redirect('catalog:activate_subscription', plan_code=plan_code)
    

    start_date = timezone.now()
    
    active_subs = UserSubscription.get_active_subscriptions(cinema_user).order_by('-expires_at')
    
    will_extend = False
    if active_subs.exists():
        current_sub = active_subs.first()
        if extend_after_current == 'true':
            start_date = current_sub.expires_at
            will_extend = True
        else:

            current_sub.status = 'cancelled'
            current_sub.save()
    
    expires_at = start_date + timedelta(days=plan.period_months * 30)
    
    subscription = UserSubscription.objects.create(
        id=uuid.uuid4(),
        user=cinema_user,
        plan=plan,
        status='active',
        started_at=start_date,
        expires_at=expires_at
    )

    transaction_id = payment_result.get('transaction_id', f'TXN{uuid.uuid4().hex[:8].upper()}')
    auth_code = payment_result.get('auth_code', '000000')
    
    payment = Payment.objects.create(
        id=uuid.uuid4(),
        txn_uuid=transaction_id,
        amount=plan.price,
        status='paid',
        paid_at=timezone.now(),
        subscription=subscription,
        created_at=timezone.now()
    )

    try:
        from .utils.email_sender import send_combined_email
        send_combined_email(cinema_user, payment, subscription=subscription)
        
        if will_extend:
            messages.success(request, 
                f"Оплата прошла успешно! ✅"
                f"Подписка {plan.name} будет активна с {expires_at.strftime('%d.%m.%Y')}"
                f"Подтверждение отправлено на {cinema_user.email}")
        else:
            messages.success(request, 
                f"Оплата прошла успешно! ✅"
                f"Подписка {plan.name} активирована до {expires_at.strftime('%d.%m.%Y')}"
                f"Подтверждение отправлено на {cinema_user.email}")
                
    except Exception as e:

        if will_extend:
            messages.success(request, 
                f"Оплата прошла успешно! ✅"
                f"Подписка {plan.name} будет активна с {expires_at.strftime('%d.%m.%Y')}"
                f"Код авторизации: {auth_code}")
        else:
            messages.success(request, 
                f"Оплата прошла успешно! ✅"
                f"Подписка {plan.name} активирована до {expires_at.strftime('%d.%m.%Y')}"
                f"Код авторизации: {auth_code}")
    
    return redirect('catalog:subscribe')

@login_required
@require_POST
def cancel_subscription(request):
    """Отмена подписки"""
    subscription_id = request.POST.get('subscription_id')
    
    try:
        cinema_user = CinemaUser.objects.get(login=request.user.username)
    except CinemaUser.DoesNotExist:
        messages.error(request, "Пользователь не найден в системе")
        return redirect('catalog:subscribe')
    

    if subscription_id:
        try:
            subscription = UserSubscription.objects.get(
                id=subscription_id,
                user=cinema_user,
                status='active'
            )
        except UserSubscription.DoesNotExist:
            messages.warning(request, "Подписка не найдена")
            return redirect('catalog:subscribe')
    else:

        subscription = UserSubscription.get_active_subscriptions(cinema_user).first()
    
    if not subscription:
        messages.warning(request, "Нет активной подписки для отмены")
        return redirect('catalog:subscribe')
    

    if not subscription.can_be_cancelled:
        if subscription.days_since_start > 14:
            messages.error(request, "Подписку нельзя отменить: прошло более 14 дней с начала действия")
        else:
            messages.error(request, "Подписка уже не активна или не может быть отменена")
        return redirect('catalog:subscribe')
    
 
    subscription.status = 'cancelled'
    subscription.save()
    
    messages.success(request, f"Подписка '{subscription.plan.name}' успешно отменена. Действует до {subscription.expires_at.strftime('%d.%m.%Y')}")
    return redirect('catalog:subscribe')


def search(request):
    """Обработка поиска"""
    query = request.GET.get('q', '').strip()
    
    if not query:
        return redirect('catalog:main')
    

    results = Content.objects.filter(
        Q(title__icontains=query) | 
        Q(description__icontains=query)
    ).select_related('cover_image', 'cover_image_wide')[:50]
    

    ratings = services.rating_map([c.id for c in results]) if results else {}
    
    def to_item(c):
        is_free = bool(c.is_free)
        price = float(getattr(c, "price", 0) or 0)
        
        if is_free:
            cta_label = "Смотреть"
            cta_href = reverse('catalog:content_detail', args=[c.id])
        elif 0 < price <= 1:
            cta_label = "По подписке"
            cta_href = reverse('catalog:subscribe')
        else:
            cta_label = "Купить"
            cta_href = reverse('catalog:purchase_start', args=[c.id])
        
        return {
            "id": c.id,
            "title": c.title,
            "poster_url": (c.cover_image.url if c.cover_image else ""),
            "rating": float(ratings.get(c.id) or 0.0),
            "year": c.release_year,
            "type": c.type,
            "kind_display": "Фильм" if c.type == "movie" else "Сериал",
            "description": (c.description[:180] + "…") if len(c.description) > 180 else c.description,
            "is_free": is_free,
            "is_subscription": 0 < price <= 1,
            "price": price,
            "cta_label": cta_label,
            "cta_href": cta_href,
        }

    exact_match = None
    other_results = []
    
    for c in results:
        item = to_item(c)
        

        if item['title'].lower() == query.lower():
            exact_match = item

        elif item['title'].lower().startswith(query.lower()):
            if exact_match is None:
                exact_match = item
            else:
                other_results.append(item)
        else:
            other_results.append(item)

    if not exact_match and other_results:
        exact_match = other_results[0]
        other_results = other_results[1:]

    if exact_match and not other_results:
        other_results = []
    
    context = {
        'query': query,
        'exact_match': exact_match,
        'results': other_results,
        'count': len(results),
    }
    
    return render(request, 'catalog/search.html', context)

def rutube_embed_page(request, video_id):
    """Страница для встраивания Rutube через JS обход"""
    html = f'''
    <!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Rutube Video</title>
    <style>
        body, html {{ 
            margin: 0; 
            padding: 0; 
            width: 100%; 
            height: 100%; 
            overflow: hidden;
            background: #000;
        }}
        .container {{
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }}
        iframe {{
            width: 100%;
            height: 100%;
            border: none;
        }}
        .fallback {{
            color: white;
            text-align: center;
            padding: 20px;
        }}
        .fallback a {{
            color: #4CAF50;
            text-decoration: none;
            font-weight: bold;
            font-size: 18px;
            padding: 10px 20px;
            background: rgba(255,255,255,0.1);
            border-radius: 5px;
            margin-top: 20px;
            display: inline-block;
        }}
        .fallback a:hover {{
            background: rgba(255,255,255,0.2);
        }}
    </style>
</head>
<body>
    <div class="container">
        <iframe 
            id="rutube-frame"
            src="https://rutube.ru/play/embed/{video_id}" 
            allow="autoplay; encrypted-media; fullscreen"
            scrolling="no"
            referrerpolicy="no-referrer"
            onerror="showFallback()"
        ></iframe>
        
        <div class="fallback" id="fallback" style="display: none;">
            <h3>Не удалось загрузить видео</h3>
            <p>Rutube блокирует встраивание видео на другие сайты</p>
            <a href="https://rutube.ru/video/{video_id}/" target="_blank">
                ▶ Смотреть на Rutube
            </a>
        </div>
    </div>
    
    <script>
        function showFallback() {{
            document.getElementById('rutube-frame').style.display = 'none';
            document.getElementById('fallback').style.display = 'block';
        }}
        
        // Пытаемся обойти X-Frame-Options
        document.getElementById('rutube-frame').onload = function() {{
            try {{
                // Пробуем получить доступ к содержимому iframe
                var iframeDoc = this.contentDocument || this.contentWindow.document;
                if (!iframeDoc || iframeDoc.location.href === 'about:blank') {{
                    showFallback();
                }}
            }} catch (e) {{
                // Если ошибка доступа (из-за политики безопасности)
                showFallback();
            }}
        }};
        
        // Если iframe не загрузился за 3 секунды
        setTimeout(function() {{
            var iframe = document.getElementById('rutube-frame');
            try {{
                var iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                if (!iframeDoc || iframeDoc.body.innerHTML.length < 100) {{
                    showFallback();
                }}
            }} catch (e) {{
                showFallback();
            }}
        }}, 3000);
    </script>
</body>
</html>
    '''