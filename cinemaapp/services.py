import requests
from .models import Genre, Content, ContentGenre, VContentWithRating, WatchHistory, Episode, Season, Watchlist, Episode
from django.db.models import Count, Prefetch, Max, Exists, OuterRef
from typing import Iterable, List, Dict, Optional
from cinemaapp.pguser import current_pg_user_uuid
from django.db import connection, transaction
from cinemaapp.models import Watchlist, ContentGenre
from django.utils import timezone
from uuid import UUID
import re

def list_genres_non_empty(order_by='items_desc'):
    """Получить жанры с контентом (без prefetch_related)"""
    from django.db import connection
    
    query = """
        SELECT g.id, g.name, COUNT(cg.content_id) as items_cnt
        FROM cinema.genres g
        LEFT JOIN cinema.content_genres cg ON g.id = cg.genre_id
        GROUP BY g.id, g.name
        HAVING COUNT(cg.content_id) > 0
    """
    
    if order_by == 'items_desc':
        query += " ORDER BY items_cnt DESC, g.name"
    else:
        query += " ORDER BY g.name"
    
    with connection.cursor() as cur:
        cur.execute(query)
        results = []
        for row in cur.fetchall():
            genre = Genre(id=row[0], name=row[1])

            genre.items_cnt = row[2]
            results.append(genre)
    
    return results

def list_content_by_genre(genre: Genre, limit=20, group='all'):
    """Получить контент по жанру (упрощенная версия)"""
    from django.db import connection
    
    query = """
        SELECT DISTINCT c.id, c.type, c.title, c.release_year, c.description, 
               c.is_free, c.price, c.cover_image_id, c.cover_image_wide_id,
               c.trailer_id, c.video_id, c.created_at, c.updated_at
        FROM cinema.content c
        INNER JOIN cinema.content_genres cg ON c.id = cg.content_id
        WHERE cg.genre_id = %s
    """
    
    params = [str(genre.id)]
    
    if group == 'movies':
        query += " AND c.type = 'movie'"
    elif group == 'series':
        query += " AND c.type = 'series'"
    
    query += " ORDER BY c.release_year DESC, c.title LIMIT %s"
    params.append(limit)
    
    with connection.cursor() as cur:
        cur.execute(query, params)
        columns = [col[0] for col in cur.description]
        results = []
        
        for row in cur.fetchall():
            row_dict = dict(zip(columns, row))
            

            from .models import Content, MediaAsset
            content = Content(
                id=row_dict['id'],
                type=row_dict['type'],
                title=row_dict['title'],
                release_year=row_dict['release_year'],
                description=row_dict['description'],
                is_free=row_dict['is_free'],
                price=row_dict['price']
            )
            

            if row_dict['cover_image_id']:
                content.cover_image_id = row_dict['cover_image_id']
                content.cover_image = MediaAsset(id=row_dict['cover_image_id'])
            
            if row_dict['cover_image_wide_id']:
                content.cover_image_wide_id = row_dict['cover_image_wide_id']
                content.cover_image_wide = MediaAsset(id=row_dict['cover_image_wide_id'])
            
            if row_dict['trailer_id']:
                content.trailer_id = row_dict['trailer_id']
                content.trailer = MediaAsset(id=row_dict['trailer_id'])
            
            if row_dict['video_id']:
                content.video_id = row_dict['video_id']
                content.video = MediaAsset(id=row_dict['video_id'])
            
            results.append(content)
    
    return results

def build_genre_sections(limit_sections=12, limit_per_genre=20, group='all'):
    """Построить секции по жанрам (упрощенная версия)"""
    sections = []

    genres = list_genres_non_empty(order_by='items_desc')
    
    for g in genres[:limit_sections]:

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
    """Получить контент с загруженными медиа URL"""
    from django.db import connection
    
    query = """
        SELECT c.id, c.type, c.title, c.release_year, c.description, 
               c.is_free, c.price, c.cover_image_id, c.cover_image_wide_id,
               c.trailer_id, c.video_id, c.created_at, c.updated_at
        FROM cinema.content c
        WHERE 1=1
    """
    
    params = []
    
    if group == "movies": 
        query += " AND c.type = 'movie'"
    elif group == "series": 
        query += " AND c.type = 'series'"
    
    query += " ORDER BY c.release_year DESC, c.title LIMIT %s"
    params.append(limit)
    
    with connection.cursor() as cur:
        cur.execute(query, params)
        columns = [col[0] for col in cur.description]
        results = []
        
        for row in cur.fetchall():
            row_dict = dict(zip(columns, row))

            from .models import Content
            content = Content(
                id=row_dict['id'],
                type=row_dict['type'],
                title=row_dict['title'],
                release_year=row_dict['release_year'],
                description=row_dict['description'],
                is_free=row_dict['is_free'],
                price=row_dict['price']
            )
 
            if row_dict['cover_image_id']:
                content.cover_image_id = row_dict['cover_image_id']
            if row_dict['cover_image_wide_id']:
                content.cover_image_wide_id = row_dict['cover_image_wide_id']
            if row_dict['trailer_id']:
                content.trailer_id = row_dict['trailer_id']
            if row_dict['video_id']:
                content.video_id = row_dict['video_id']
            
            results.append(content)
    

    return _load_media_for_content(results)

def get_content(pk):
    """Получить контент по ID (упрощенная версия)"""
    from django.db import connection
    
    query = """
        SELECT c.id, c.type, c.title, c.release_year, c.description, 
               c.is_free, c.price, c.cover_image_id, c.cover_image_wide_id,
               c.trailer_id, c.video_id, c.created_at, c.updated_at
        FROM cinema.content c
        WHERE c.id = %s
    """
    
    with connection.cursor() as cur:
        cur.execute(query, [str(pk)])
        columns = [col[0] for col in cur.description]
        row = cur.fetchone()
        
        if not row:
            from django.http import Http404
            raise Http404("Content not found")
        
        row_dict = dict(zip(columns, row))
  
        from .models import Content, MediaAsset
        content = Content(
            id=row_dict['id'],
            type=row_dict['type'],
            title=row_dict['title'],
            release_year=row_dict['release_year'],
            description=row_dict['description'],
            is_free=row_dict['is_free'],
            price=row_dict['price']
        )

        if row_dict['cover_image_id']:
            content.cover_image_id = row_dict['cover_image_id']
            content.cover_image = MediaAsset(id=row_dict['cover_image_id'])
        
        if row_dict['cover_image_wide_id']:
            content.cover_image_wide_id = row_dict['cover_image_wide_id']
            content.cover_image_wide = MediaAsset(id=row_dict['cover_image_wide_id'])
        
        if row_dict['trailer_id']:
            content.trailer_id = row_dict['trailer_id']
            content.trailer = MediaAsset(id=row_dict['trailer_id'])
        
        if row_dict['video_id']:
            content.video_id = row_dict['video_id']
            content.video = MediaAsset(id=row_dict['video_id'])
        
        return content

def rating_map(ids):
    """Получить рейтинги для списка ID"""
    from django.db import connection
    
    if not ids:
        return {}

    id_strs = [str(id) for id in ids]
    
    query = """
        SELECT id, avg_rating
        FROM cinema.v_content_with_rating
        WHERE id = ANY(%s)
    """
    
    with connection.cursor() as cur:
        cur.execute(query, [id_strs])
        return {row[0]: row[1] for row in cur.fetchall()}

def to_ctx_item(c):
    """Преобразовать объект Content в словарь для шаблона"""
    backdrop_url = ""
    if getattr(c, "cover_image_wide", None):
        backdrop_url = c.cover_image_wide.url if hasattr(c.cover_image_wide, 'url') else ""
    elif getattr(c, "cover_image", None):
        backdrop_url = c.cover_image.url if hasattr(c.cover_image, 'url') else ""
    
    return {
        "id": c.id,
        "title": c.title,
        "backdrop_url": backdrop_url,
        "poster_url": c.cover_image.url if c.cover_image and hasattr(c.cover_image, 'url') else "",
        "is_free": c.is_free,
    }

def get_continue_watch_for_user(django_user, limit=20):
    """Получить контент для продолжения просмотра"""
    if not getattr(django_user, "is_authenticated", False):
        return []

    from django.db import connection
    
    query = """
        SELECT DISTINCT ON (wh.content_id) wh.content_id, wh.watched_at
        FROM cinema.watch_history wh
        JOIN cinema.users u ON u.id = wh.user_id
        WHERE u.login = %s
        ORDER BY wh.content_id, wh.watched_at DESC
        LIMIT %s
    """
    
    with connection.cursor() as cur:
        cur.execute(query, [django_user.username, limit])
        content_ids = [row[0] for row in cur.fetchall()]
    
    if not content_ids:
        return []

    return list_content_by_ids(content_ids)

def list_content_by_ids(ids, limit=None):
    """Получить контент по списку ID"""
    if not ids:
        return []
    
    from django.db import connection
    
    id_strs = [str(id) for id in ids]
    
    query = """
        SELECT c.id, c.type, c.title, c.release_year, c.description, 
               c.is_free, c.price, c.cover_image_id, c.cover_image_wide_id,
               c.trailer_id, c.video_id, c.created_at, c.updated_at
        FROM cinema.content c
        WHERE c.id = ANY(%s)
    """
    
    params = [id_strs]
    
    if limit:
        query += " LIMIT %s"
        params.append(limit)
    
    with connection.cursor() as cur:
        cur.execute(query, params)
        columns = [col[0] for col in cur.description]
        results = []
        
        for row in cur.fetchall():
            row_dict = dict(zip(columns, row))
            
            from .models import Content, MediaAsset
            content = Content(
                id=row_dict['id'],
                type=row_dict['type'],
                title=row_dict['title'],
                release_year=row_dict['release_year'],
                description=row_dict['description'],
                is_free=row_dict['is_free'],
                price=row_dict['price']
            )
            
            if row_dict['cover_image_id']:
                content.cover_image_id = row_dict['cover_image_id']
                content.cover_image = MediaAsset(id=row_dict['cover_image_id'])
            
            if row_dict['cover_image_wide_id']:
                content.cover_image_wide_id = row_dict['cover_image_wide_id']
                content.cover_image_wide = MediaAsset(id=row_dict['cover_image_wide_id'])
            
            results.append(content)
    
    return results

def can_watch(dj_user, content) -> bool:

    if bool(getattr(content, "is_free", False)):
        return True

    if not getattr(dj_user, "is_authenticated", False):
        return False

    cinema_user_id = _ensure_cinema_user(dj_user)


    with connection.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM cinema.purchases
            WHERE user_id=%s AND content_id=%s
            LIMIT 1
        """, [cinema_user_id, str(content.id)])
        purchased = (cur.fetchone() is not None)

    if purchased:
        return True


    price = float(getattr(content, "price", 0) or 0.0)
    in_subscription = (not getattr(content, "is_free", False)) and (price <= 1.0)

    if in_subscription:

        return has_subscription_access(cinema_user_id)

    return False

def _user_has_active_subscription(cinema_user_id) -> bool:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM cinema.user_subscriptions
            WHERE user_id=%s
              AND status='active'
              AND (
                  -- Текущая активная подписка
                  (expires_at IS NULL OR expires_at > now())
                  OR
                  -- Будущая подписка (уже оплачена, но еще не началась)
                  started_at > now()
              )
            LIMIT 1
        """, [cinema_user_id])
        return cur.fetchone() is not None

    candidates = ["subscriptions", "user_subscriptions", "memberships",
                  "plan_users", "subscription_users", "subscriptions_users"]
    table = next((t for t in candidates if t in tables), None)
    if not table:
        return False

    def pick(cols):
        with connection.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='cinema' AND table_name=%s
            """, [table])
            have = {r[0] for r in cur.fetchall()}
        for c in cols:
            if c in have:
                return c
        return None

    user_col   = pick(["user_id","uid","customer_id"])
    active_col = pick(["is_active","active"])
    status_col = pick(["status"])
    until_col  = pick(["paid_till","paid_until","valid_until","expires_at","active_until","ends_at"])

    if not user_col:
        return False

    with connection.cursor() as cur:
        if until_col:
            cur.execute(
                f"SELECT 1 FROM cinema.{table} WHERE {user_col}=%s AND {until_col} >= now() LIMIT 1",
                [cinema_user_id]
            )
            if cur.fetchone(): return True

        if active_col:
            cur.execute(
                f"SELECT 1 FROM cinema.{table} WHERE {user_col}=%s AND {active_col}=true LIMIT 1",
                [cinema_user_id]
            )
            if cur.fetchone(): return True

        if status_col:
            cur.execute(
                f"SELECT 1 FROM cinema.{table} WHERE {user_col}=%s AND lower({status_col}) IN ('active','paid','trial','trialing') LIMIT 1",
                [cinema_user_id]
            )
            if cur.fetchone(): return True

    return False

def dictfetchone(cur):
    row = cur.fetchone()
    if not row:
        return None
    cols = [c[0] for c in cur.description]
    return {cols[i]: row[i] for i in range(len(cols))}

def _cinema_tables():
    with connection.cursor() as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='cinema'
        """)
        return {r[0] for r in cur.fetchall()}

def _columns(schema, table):
    with connection.cursor() as cur:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
        """, [schema, table])
        return {r[0] for r in cur.fetchall()}

def _detect_subscription_table():
    return {
        "table":   "user_subscriptions",
        "user":    "user_id",
        "plan":    "plan_id",
        "status":  "status",
        "until":   "expires_at",
        "created": "started_at",
        "active":  None,
        "auto":    None,
    }

def _get_plan_title(plan_id):
    if not plan_id:
        return None
    with connection.cursor() as cur:
        cur.execute("SELECT name FROM cinema.subscription_plans WHERE id=%s", [plan_id])
        row = cur.fetchone()
    return row[0] if row else None

def get_user_subscription_info(dj_user):
    info = {"is_active": False, "until": None, "status": None, "plan_title": None, "raw": None}
    if not getattr(dj_user, "is_authenticated", False):
        return info

    cinema_user_id = _ensure_cinema_user(dj_user)

    m = _detect_subscription_table()
    if not m:
        return info

    order_expr = (
        f"COALESCE({m['until']}, now()) DESC"
        if m['until'] else
        f"{m['created']} DESC"
    )

    with connection.cursor() as cur:
        cur.execute(
            f"SELECT * FROM cinema.{m['table']} WHERE {m['user']}=%s ORDER BY {order_expr} LIMIT 1",
            [cinema_user_id]
        )
        row = dictfetchone(cur)

    if not row:
        return info

    now     = timezone.now()
    until   = row.get(m['until'])   if m['until']   else None
    started = row.get(m['created']) if m['created'] else None
    status  = (row.get(m['status']) or "").lower()  if m['status'] else None

    is_active = (
        (status == "active") and
        (
            (until is None or until >= now) or
            (started and started > now)
        )
    )

    plan_title = _get_plan_title(row.get(m['plan'])) if m['plan'] else None

    info.update({
        "is_active": is_active,
        "until": until,
        "status": status,
        "plan_title": plan_title,
        "raw": row,
    })
    return info

def _ensure_cinema_user(user):
    """
    Возвращает UUID из cinema.users для текущего Django-пользователя.
    Если записи нет — создаёт её (минимально валидную).
    """
    login_raw = user.username or f"user{user.id}"

    login = re.sub(r"[^A-Za-z0-9_.-]", "_", login_raw)[:32]
    if len(login) < 5:
        login = f"user{user.id:04d}"

 
    email = user.email or f"{login}@local.test"

    with connection.cursor() as cur:
        cur.execute("SELECT id FROM cinema.users WHERE login=%s", [login])
        row = cur.fetchone()
        if row:
            return row[0]


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

        cur.execute(
            """
            INSERT INTO cinema.content_reviews (user_id, content_id, rating)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, content_id) DO UPDATE
            SET rating = EXCLUDED.rating, updated_at = now()
            """,
            [cinema_user_id, str(content_id), rating],
        )

        cur.execute(
            "SELECT COALESCE(ROUND(AVG(rating)::numeric, 1), 0) "
            "FROM cinema.content_reviews WHERE content_id=%s",
            [str(content_id)],
        )
        avg = cur.fetchone()[0]

    return float(avg or 0)


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
    """Получить рейтинг для конкретного контента"""
    from django.db import connection
    
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
        ts_col = 'created_at'

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
    
def _get_media_url(media_id):
    """Получить URL медиафайла по ID"""
    if not media_id:
        return ""
    
    from django.db import connection
    with connection.cursor() as cur:
        cur.execute("SELECT url FROM cinema.media_assets WHERE id = %s", [str(media_id)])
        row = cur.fetchone()
        return row[0] if row else ""

def _load_media_for_content(content_list):
    """Загрузить медиа URL для списка контента"""
    if not content_list:
        return content_list
    
    from django.db import connection
    from .models import MediaAsset

    media_ids = set()
    for content in content_list:
        if hasattr(content, 'cover_image_id') and content.cover_image_id:
            media_ids.add(content.cover_image_id)
        if hasattr(content, 'cover_image_wide_id') and content.cover_image_wide_id:
            media_ids.add(content.cover_image_wide_id)
        if hasattr(content, 'trailer_id') and content.trailer_id:
            media_ids.add(content.trailer_id)
        if hasattr(content, 'video_id') and content.video_id:
            media_ids.add(content.video_id)
    
    if not media_ids:
        return content_list
    

    media_urls = {}
    id_strs = [str(id) for id in media_ids]
    with connection.cursor() as cur:
        cur.execute("""
            SELECT id, url FROM cinema.media_assets 
            WHERE id = ANY(%s)
        """, [id_strs])
        media_urls = {row[0]: row[1] for row in cur.fetchall()}

    for content in content_list:
        if hasattr(content, 'cover_image_id') and content.cover_image_id:
            url = media_urls.get(content.cover_image_id)
            if url:
                if not content.cover_image:
                    content.cover_image = MediaAsset(id=content.cover_image_id)
                content.cover_image.url = url
        
        if hasattr(content, 'cover_image_wide_id') and content.cover_image_wide_id:
            url = media_urls.get(content.cover_image_wide_id)
            if url:
                if not content.cover_image_wide:
                    content.cover_image_wide = MediaAsset(id=content.cover_image_wide_id)
                content.cover_image_wide.url = url
        
        if hasattr(content, 'trailer_id') and content.trailer_id:
            url = media_urls.get(content.trailer_id)
            if url:
                if not content.trailer:
                    content.trailer = MediaAsset(id=content.trailer_id)
                content.trailer.url = url
        
        if hasattr(content, 'video_id') and content.video_id:
            url = media_urls.get(content.video_id)
            if url:
                if not content.video:
                    content.video = MediaAsset(id=content.video_id)
                content.video.url = url
    
    return content_list

def get_rutube_video_url(rutube_url):
    """Попытаться получить прямую ссылку на видео Rutube"""
    try:

        video_id = None
        patterns = [
            r'rutube\.ru/video/([a-f0-9]{32})',
            r'rutube\.ru/play/embed/([a-f0-9]{32})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, rutube_url, re.IGNORECASE)
            if match:
                video_id = match.group(1)
                break
        
        if not video_id:
            return None

        api_url = f"https://rutube.ru/api/play/options/{video_id}/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://rutube.ru/',
            'Accept': 'application/json',
        }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
 
            if 'video_balancer' in data:
                if 'mp4' in data['video_balancer']:
                    return data['video_balancer']['mp4']['url']
            
            if 'video' in data:
                if 'url' in data['video']:
                    return data['video']['url']

            html_url = f"https://rutube.ru/video/{video_id}/"
            html_response = requests.get(html_url, headers=headers)
            html = html_response.text

            json_pattern = r'window\.__DATA__\s*=\s*({.*?});'
            match = re.search(json_pattern, html, re.DOTALL)
            
            if match:
                import json
                data_json = match.group(1)
                data = json.loads(data_json)

                if 'video' in data and 'url' in data['video']:
                    return data['video']['url']
        
    except Exception as e:
        print(f"Error getting Rutube URL: {e}")
    
    return None

def _user_has_current_subscription(cinema_user_id) -> bool:
    """Проверяет, есть ли ТЕКУЩАЯ активная подписка (для доступа к контенту)"""
    return has_subscription_access(cinema_user_id)

def _user_has_any_active_subscription(cinema_user_id) -> bool:
    """Проверяет, есть ли ЛЮБАЯ активная подписка (текущая ИЛИ будущая) - для отображения"""

    now = timezone.now()
    
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM cinema.user_subscriptions
            WHERE user_id=%s
              AND status='active'
              AND (
                  -- Текущая активная подписка
                  (started_at <= %s AND (expires_at IS NULL OR expires_at > %s))
                  OR
                  -- Будущая подписка (только для отображения!)
                  started_at > %s
              )
            LIMIT 1
        """, [cinema_user_id, now, now, now])
        return cur.fetchone() is not None

def has_subscription_access(cinema_user_id) -> bool:
    """Проверяет, есть ли доступ к контенту по подписке ПРЯМО СЕЙЧАС (действующая активная подписка)"""
    now = timezone.now()
    
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM cinema.user_subscriptions
            WHERE user_id=%s
              AND status='active'
              AND started_at <= %s  -- Подписка УЖЕ началась
              AND (expires_at IS NULL OR expires_at > %s)  -- Еще не истекла
            LIMIT 1
        """, [cinema_user_id, now, now])
        return cur.fetchone() is not None
    
def has_future_subscription(cinema_user_id) -> bool:
    """Проверяет, есть ли будущая подписка (только для отображения в интерфейсе)"""
    now = timezone.now()
    
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM cinema.user_subscriptions
            WHERE user_id=%s
              AND status='active'
              AND started_at > %s  -- Подписка еще НЕ началась
            LIMIT 1
        """, [cinema_user_id, now])
        return cur.fetchone() is not None
    
def get_active_subscription_now(cinema_user_id):
    """Возвращает текущую активную подписку (действующую сейчас)"""
    now = timezone.now()
    
    with connection.cursor() as cur:
        cur.execute("""
            SELECT us.*, sp.name as plan_name
            FROM cinema.user_subscriptions us
            JOIN cinema.subscription_plans sp ON sp.id = us.plan_id
            WHERE us.user_id=%s
              AND us.status='active'
              AND us.started_at <= %s  -- Уже началась
              AND (us.expires_at IS NULL OR us.expires_at > %s)  -- Еще не истекла
            ORDER BY us.expires_at DESC NULLS LAST
            LIMIT 1
        """, [cinema_user_id, now, now])
        
        row = cur.fetchone()
        if row:
            columns = [col[0] for col in cur.description]
            return dict(zip(columns, row))
    return None

def get_subscription_info(cinema_user_id):
    """Полная информация о всех активных подписках пользователя"""
    now = timezone.now()
    
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 
                us.id,
                us.plan_id,
                sp.name as plan_name,
                us.started_at,
                us.expires_at,
                us.status,
                -- Статус доступа
                CASE 
                    WHEN us.started_at <= %s AND (us.expires_at IS NULL OR us.expires_at > %s) 
                    THEN 'active_now'  -- Действует сейчас
                    WHEN us.started_at > %s 
                    THEN 'future'      -- Будущая подписка
                    ELSE 'expired_or_other'
                END as access_status
            FROM cinema.user_subscriptions us
            JOIN cinema.subscription_plans sp ON sp.id = us.plan_id
            WHERE us.user_id=%s
              AND us.status='active'
            ORDER BY us.started_at DESC
        """, [now, now, now, cinema_user_id])
        
        columns = [col[0] for col in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        
    return rows