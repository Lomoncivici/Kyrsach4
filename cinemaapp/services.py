from .models import Content, MediaAsset, ContentGenre, Genre, VContentWithRating, WatchHistory, Episode, Season, Watchlist, Episode,  ContentReview
from django.db.models import Prefetch, OuterRef, Subquery, F, Q, Max
from django.db import connection, transaction

import re
from django.db import connection

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

def to_ctx_item(c):
    return {
        "id": c.id,
        "title": c.title,
        "backdrop_url": c.cover_image.url if c.cover_image else "",
        "poster_url": c.cover_image.url if c.cover_image else "",
        "is_free": c.is_free,
    }

def get_continue_watch_for_user(django_user, limit=20):
    if not getattr(django_user, "is_authenticated", False):
        return []

    wh = (
        WatchHistory.objects
        .filter(user__login=django_user.username)
        .values("content_id")
        .annotate(last=Max("watched_at"))
        .order_by("-last")[:limit]
    )

    content_ids = [row["content_id"] for row in wh]
    if not content_ids:
        return []

    order = {cid: i for i, cid in enumerate(content_ids)}
    qs = (
        Content.objects
        .select_related("cover_image", "trailer", "video")
        .filter(id__in=content_ids)
    )
    return sorted(qs, key=lambda c: order[c.id])

def can_watch(dj_user, content) -> bool:
    # бесплатный — доступен всем
    if bool(getattr(content, "is_free", False)):
        return True

    # неавторизованным нельзя
    if not getattr(dj_user, "is_authenticated", False):
        return False

    # получаем UUID пользователя из cinema.users
    cinema_user_id = _ensure_cinema_user(dj_user)

    # доступ через покупку (если у тебя есть поддержка подписок — можешь добавить отдельную проверку)
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM cinema.purchases
            WHERE user_id=%s AND content_id=%s
            LIMIT 1
        """, [cinema_user_id, str(content.id)])
        return cur.fetchone() is not None

def _ensure_cinema_user(user):
    """
    Возвращает UUID из cinema.users для текущего Django-пользователя.
    Если записи нет — создаёт её (минимально валидную).
    """
    login_raw = user.username or f"user{user.id}"
    # login_domain: 5..32 символов, [A-Za-z0-9_.-]
    login = re.sub(r"[^A-Za-z0-9_.-]", "_", login_raw)[:32]
    if len(login) < 5:
        login = f"user{user.id:04d}"

    # валидный email для email_domain (если нет — подставим локальный)
    email = user.email or f"{login}@local.test"

    with connection.cursor() as cur:
        cur.execute("SELECT id FROM cinema.users WHERE login=%s", [login])
        row = cur.fetchone()
        if row:
            return row[0]

        # password_hash у нас проверяется только по префиксу, этого достаточно
        cur.execute(
            """
            INSERT INTO cinema.users (email, login, password_hash)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            [email, login, "$argon2"],
        )
        return cur.fetchone()[0]

@transaction.atomic
def upsert_rating(dj_user, content_id, rating: int):
    """
    Сохраняет/обновляет оценку и возвращает средний рейтинг по контенту.
    """
    cinema_user_id = _ensure_cinema_user(dj_user)
    rating = max(1, min(5, int(rating)))

    with connection.cursor() as cur:
        # upsert оценки
        cur.execute(
            """
            INSERT INTO cinema.content_reviews (user_id, content_id, rating)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, content_id) DO UPDATE
            SET rating = EXCLUDED.rating, updated_at = now()
            """,
            [cinema_user_id, str(content_id), rating],
        )
        # среднее
        cur.execute(
            "SELECT COALESCE(ROUND(AVG(rating)::numeric, 1), 0) "
            "FROM cinema.content_reviews WHERE content_id=%s",
            [str(content_id)],
        )
        avg = cur.fetchone()[0]

    return float(avg or 0)

def watchlist_toggle(user, content_id) -> bool:
    """
    Добавить/удалить из избранного. Возвращает True если стало В ИЗБРАННОМ.
    """
    obj, created = Watchlist.objects.get_or_create(user_id=user.id, content_id=content_id,
                                                   defaults={"created_at": None})
    if created:
        return True
    obj.delete()
    return False

def series_tree(content: Content):
    """
    Вернуть структуру сезонов/эпизодов для шаблона.
    """
    seasons = (Season.objects.filter(content=content)
               .order_by("season_num")
               .select_related())
    result = []
    eps = (Episode.objects
           .filter(season__content=content)
           .select_related("video", "season")
           .order_by("season__season_num", "episode_num"))
    episodes_by_season = {}
    for e in eps:
        episodes_by_season.setdefault(e.season_id, []).append({
            "id": e.id,
            "num": e.episode_num,
            "title": e.title,
            "duration": e.duration_sec,
            "video_url": e.video.url if e.video else "",
            "season_num": e.season.season_num,
        })
    for s in seasons:
        result.append({
            "id": s.id,
            "num": s.season_num,
            "episodes": episodes_by_season.get(s.id, []),
        })
    return result

def rating_for(content_id):
    with connection.cursor() as cur:
        cur.execute("""
            SELECT ROUND(AVG(rating)::numeric, 2)
            FROM cinema.content_reviews
            WHERE content_id = %s
        """, [str(content_id)])
        row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0

def _table_exists(qualified: str) -> bool:
    # qualified = 'schema.table'
    with connection.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", [qualified])
        return cur.fetchone()[0] is not None

def _first_existing_column(schema: str, table: str, candidates):
    with connection.cursor() as cur:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
        """, [schema, table])
        cols = {r[0] for r in cur.fetchall()}
    for c in candidates:
        if c in cols:
            return c
    return None

def list_user_purchases(dj_user):
    cid = _ensure_cinema_user(dj_user)
    with connection.cursor() as cur:
        cur.execute("""
            SELECT content_id, purchased_at
            FROM cinema.purchases
            WHERE user_id=%s
            ORDER BY purchased_at DESC NULLS LAST
        """, [cid])
        rows = cur.fetchall()
    return [{'content_id': r[0], 'purchased_at': r[1]} for r in rows]

def list_user_ratings(dj_user):
    cid = _ensure_cinema_user(dj_user)
    with connection.cursor() as cur:
        cur.execute("""
            SELECT content_id, rating, updated_at
            FROM cinema.content_reviews
            WHERE user_id=%s
            ORDER BY updated_at DESC NULLS LAST
        """, [cid])
        rows = cur.fetchall()
    return [{'content_id': r[0], 'rating': int(r[1]), 'updated_at': r[2]} for r in rows]

def list_user_history(dj_user):
    """Построит историю по первой найденной таблице из набора вариантов."""
    cid = _ensure_cinema_user(dj_user)
    options = ['watch_history', 'view_history', 'content_views', 'views', 'history']
    table = None
    for t in options:
        if _table_exists(f'cinema.{t}'):
            table = t
            break
    if not table:
        return []
    ts_col = _first_existing_column('cinema', table,
            ['viewed_at', 'watched_at', 'created_at', 'updated_at', 'time_at', 'timestamp'])
    if not ts_col:
        ts_col = 'created_at'  # на всякий случай

    with connection.cursor() as cur:
        cur.execute(f"""
            SELECT content_id, {ts_col} AS at
            FROM cinema.{table}
            WHERE user_id=%s
            ORDER BY {ts_col} DESC NULLS LAST
            LIMIT 500
        """, [cid])
        rows = cur.fetchall()
    return [{'content_id': r[0], 'viewed_at': r[1]} for r in rows]
