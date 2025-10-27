from .models import Genre, Content, ContentGenre, VContentWithRating, WatchHistory, Episode, Season, Watchlist, Episode
from django.db.models import Count, Prefetch, Max, Exists, OuterRef
from typing import Iterable, List, Dict, Optional
from cinemaapp.pguser import current_pg_user_uuid
from django.db import connection, transaction
from cinemaapp.models import Watchlist, ContentGenre
from uuid import UUID
import re

def list_genres_non_empty(order_by='items_desc'):
    qs = (Genre.objects
          .annotate(items_cnt=Count('contentgenre'))
          .filter(items_cnt__gt=0))
    if order_by == 'items_desc':
        qs = qs.order_by('-items_cnt', 'name')
    else:
        qs = qs.order_by('name')
    return qs

def list_content_by_genre(genre: Genre, limit=20, group='all'):
    qs = (Content.objects
          .filter(contentgenre__genre=genre)
          .select_related('cover_image','cover_image_wide','trailer','video')
          .prefetch_related(Prefetch('contentgenre_set',
                        queryset=ContentGenre.objects.select_related('genre'))))
    if group == 'movies':
        qs = qs.filter(type='movie')
    elif group == 'series':
        qs = qs.filter(type='series')
    return qs.order_by('-release_year','title')[:limit]

def build_genre_sections(limit_sections=12, limit_per_genre=20, group='all'):
    sections = []
    for g in list_genres_non_empty(order_by='items_desc')[:limit_sections]:
        items = list_content_by_genre(g, limit=limit_per_genre, group=group)
        if items:
            sections.append({"title": g.name, "items": list(items)})
    return sections

def _pick_col(table: str, candidates: list[str]) -> str | None:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='cinema' AND table_name=%s",
            [table],
        )
        cols = {r[0] for r in cur.fetchall()}
    for c in candidates:
        if c in cols:
            return c
    return None

def _resolve_season_id(content_id, sn: int):
    sn = int(sn)
    col = _pick_col("seasons", ["season_number", "number", "seq", "position", "ord", "order_num", "index"])
    with connection.cursor() as cur:
        if col:
            cur.execute(f"SELECT id FROM cinema.seasons WHERE content_id=%s AND {col}=%s LIMIT 1", [str(content_id), sn])
        else:
            cur.execute(
                "SELECT id FROM cinema.seasons WHERE content_id=%s ORDER BY id LIMIT 1 OFFSET %s",
                [str(content_id), max(sn - 1, 0)],
            )
        row = cur.fetchone()
    return row[0] if row else None

def _resolve_episode_id(season_id, en: int):
    en = int(en)
    col = _pick_col("episodes", ["number", "episode_number", "seq", "position", "ord", "order_num", "index"])
    with connection.cursor() as cur:
        if col:
            cur.execute(f"SELECT id FROM cinema.episodes WHERE season_id=%s AND {col}=%s LIMIT 1", [str(season_id), en])
        else:
            cur.execute(
                "SELECT id FROM cinema.episodes WHERE season_id=%s ORDER BY id LIMIT 1 OFFSET %s",
                [str(season_id), max(en - 1, 0)],
            )
        row = cur.fetchone()
    return row[0] if row else None


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
        "backdrop_url": (c.cover_image_wide.url if getattr(c, "cover_image_wide", None)
                         else (c.cover_image.url if getattr(c, "cover_image", None) else "")),
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

    # доступ через покупку
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

        # password_hash проверяется только по префиксу, этого достаточно
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

# --- WATCH HISTORY

def _find_episode_id(content_id, sn: int | None, en: int | None):
    if not sn or not en:
        return None
    season_id = _resolve_season_id(content_id, int(sn))
    if not season_id:
        return None
    return _resolve_episode_id(season_id, int(en))

def save_progress(dj_user, content_id, position: int, duration: int | None,
                  sn: int = 0, en: int = 0, completed: bool = False):
    """
    Сохранить/обновить прогресс просмотра.
    Уникальность по (user_id, content_id, episode_id).
    """
    cinema_user_id = _ensure_cinema_user(dj_user)
    episode_id = _find_episode_id(content_id, sn, en)

    # нормализуем значения
    position = max(0, int(position or 0))
    duration = None if duration in (None, "", 0) else int(duration)
    completed = bool(completed)

    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO cinema.watch_history
                (user_id, content_id, episode_id, progress_sec, watched_at)
            VALUES
                (%s, %s, %s, %s, now())
            ON CONFLICT (user_id, content_id, episode_id) DO UPDATE
            SET progress_sec = EXCLUDED.progress_sec,
                watched_at   = now()
            """,
            [cinema_user_id, str(content_id), episode_id, position],
        )


def get_progress(dj_user, content_id, sn: int = 0, en: int = 0):
    """
    Вернёт последний прогресс по фильму/эпизоду.
    Ответ: { position_sec, duration_sec, is_completed }
    """
    cinema_user_id = _ensure_cinema_user(dj_user)
    episode_id = _find_episode_id(content_id, sn, en)

    with connection.cursor() as cur:
        if episode_id:
            cur.execute(
                """
                SELECT progress_sec
                FROM cinema.watch_history
                WHERE user_id=%s AND content_id=%s AND episode_id=%s
                ORDER BY watched_at DESC
                LIMIT 1
                """,
                [cinema_user_id, str(content_id), episode_id],
            )
        else:
            cur.execute(
                """
                SELECT progress_sec, duration_sec, is_completed
                FROM cinema.watch_history
                WHERE user_id=%s AND content_id=%s AND episode_id IS NULL
                ORDER BY watched_at DESC
                LIMIT 1
                """,
                [cinema_user_id, str(content_id)],
            )
        row = cur.fetchone()

    if not row:
        return {"position_sec": 0, "duration_sec": None, "is_completed": False}
    return {
        "position_sec": int(row[0] or 0),
        "duration_sec": None,
        "is_completed": False,
    }

# --- EPISODE SOURCE
def _detect_web_kind(url: str) -> str:
    u = (url or "").lower()
    if "youtu" in u:
        return "youtube"
    if "rutube" in u:
        return "rutube"
    return "web"

def episode_source(content, season_number: int, episode_number: int) -> dict:
    """
    {"ok": True/False, "kind": "file|youtube|rutube|web", "url": "<...>"}
    """
    season_id = _resolve_season_id(content.id, season_number)
    if not season_id:
        return {"ok": False, "detail": "season not found"}

    episode_id = _resolve_episode_id(season_id, episode_number)
    if not episode_id:
        return {"ok": False, "detail": "episode not found"}

    with connection.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(ma.kind,'') AS k, ma.url "
            "FROM cinema.episodes e LEFT JOIN cinema.media_assets ma ON ma.id = e.video_id "
            "WHERE e.id=%s LIMIT 1",
            [str(episode_id)],
        )
        row = cur.fetchone()

    if not row or not row[1]:
        return {"ok": False, "detail": "video url is empty"}

    kind = (row[0] or "").lower()
    url = row[1]
    if kind in ("", None, "file"):
        kind = "file"
    elif kind == "web":
        kind = _detect_web_kind(url)

    return {"ok": True, "kind": kind, "url": url}

@transaction.atomic
def watchlist_toggle(dj_user, content_id):
    cu = current_pg_user_uuid(dj_user)
    user_uuid = cu.id

    cid = UUID(str(content_id))

    row = (Watchlist.objects
           .select_for_update()
           .filter(user_id=user_uuid, content_id=cid)
           .first())

    if row:
        row.delete()
        return {"in_watchlist": False}
    else:
        Watchlist.objects.create(user_id=user_uuid, content_id=cid)
        return {"in_watchlist": True}

def series_tree(content: Content):
    """
    [{"number":1,"title":"Сезон 1","episodes":[{"number":1,"title":"Серия 1"}, ...]}, ...]
    """
    seasons = []
    s_col = _pick_col("seasons", ["season_number", "number", "seq", "position", "ord", "order_num", "index"])
    e_col = _pick_col("episodes", ["number", "episode_number", "seq", "position", "ord", "order_num", "index"])

    with connection.cursor() as cur:
        if s_col:
            cur.execute(
                f"SELECT id, COALESCE(title, 'Сезон '||{s_col}) AS t, {s_col} AS n "
                "FROM cinema.seasons WHERE content_id=%s ORDER BY n",
                [str(content.id)],
            )
        else:
            cur.execute(
                "SELECT id, COALESCE(title, 'Сезон') AS t, ROW_NUMBER() OVER(ORDER BY id) AS n "
                "FROM cinema.seasons WHERE content_id=%s ORDER BY n",
                [str(content.id)],
            )
        seasons_rows = cur.fetchall()

    for sid, stitle, sn in seasons_rows:
        episodes = []
        with connection.cursor() as cur:
            if e_col:
                cur.execute(
                    f"SELECT COALESCE(title, 'Серия '||{e_col}) AS t, {e_col} AS n "
                    "FROM cinema.episodes WHERE season_id=%s ORDER BY n",
                    [str(sid)],
                )
            else:
                cur.execute(
                    "SELECT COALESCE(title, 'Серия') AS t, ROW_NUMBER() OVER(ORDER BY id) AS n "
                    "FROM cinema.episodes WHERE season_id=%s ORDER BY n",
                    [str(sid)],
                )
            for etitle, en in cur.fetchall():
                episodes.append({"number": int(en), "title": etitle})
        seasons.append({"number": int(sn), "title": stitle, "episodes": episodes})
    return seasons

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
        ts_col = 'created_at' # на всякий случай 

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

def list_user_favorites(dj_user):
    with connection.cursor() as cur:
        cur.execute("""
            SELECT f.content_id, f.created_at
            FROM cinema.favorites f
            JOIN cinema.users u ON u.id = f.user_id
            WHERE u.login = %s
            ORDER BY f.created_at DESC
        """, [dj_user.username])
        return [{'content_id': row[0], 'created_at': row[1]} for row in cur.fetchall()]