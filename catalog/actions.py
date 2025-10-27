from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.db import connection

@login_required
def toggle_favorite(request, content_id):
    login = request.user.username
    cid = str(content_id)

    with connection.cursor() as cur:
        cur.execute("SELECT id FROM cinema.users WHERE login=%s", [login])
        row = cur.fetchone()
        if not row:
            return HttpResponseBadRequest("Пользователь не найден в cinema.users")
        user_uuid = str(row[0])

        cur.execute("""
            WITH ins AS (
                INSERT INTO cinema.favorites(user_id, content_id)
                VALUES (%s::uuid, %s::uuid)
                ON CONFLICT DO NOTHING
                RETURNING 1
            )
            DELETE FROM cinema.favorites f
            WHERE f.user_id=%s::uuid
              AND f.content_id=%s::uuid
              AND NOT EXISTS (SELECT 1 FROM ins);
        """, [user_uuid, cid, user_uuid, cid])

        cur.execute("""
            SELECT EXISTS(
              SELECT 1 FROM cinema.favorites
              WHERE user_id=%s::uuid AND content_id=%s::uuid
            )
        """, [user_uuid, cid])
        is_favorite = bool(cur.fetchone()[0])

    return JsonResponse({"ok": True, "is_favorite": is_favorite})

@login_required
def add_review(request, content_id):
    rating = int(request.POST.get("rating","0"))
    comment = request.POST.get("comment","").strip()
    if rating < 1 or rating > 5:
        return HttpResponseBadRequest("rating 1..5")
    with connection.cursor() as cur:
        # RLS-актор уже проставлен middleware
        cur.execute("""
            INSERT INTO cinema.content_reviews(user_id, content_id, rating, comment)
            VALUES ((SELECT id FROM cinema.users WHERE login=%s), %s, %s, %s)
            ON CONFLICT (user_id, content_id) DO UPDATE SET rating=EXCLUDED.rating, comment=EXCLUDED.comment
        """, [request.user.username, str(content_id), rating, comment])
    return JsonResponse({"ok": True})

@login_required
def favorite_status(request, content_id):
    login = request.user.username
    cid = str(content_id)
    with connection.cursor() as cur:
        cur.execute("SELECT id FROM cinema.users WHERE login=%s", [login])
        row = cur.fetchone()
        if not row:
            return HttpResponseBadRequest("Пользователь не найден")
        user_uuid = str(row[0])
        cur.execute("""
            SELECT EXISTS(
              SELECT 1 FROM cinema.favorites
              WHERE user_id=%s::uuid AND content_id=%s::uuid
            )
        """, [user_uuid, cid])
        is_favorite = bool(cur.fetchone()[0])
    return JsonResponse({"is_favorite": is_favorite})