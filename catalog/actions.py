from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.db import connection

@login_required
def toggle_favorite(request, content_id):
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO cinema.favorites(user_id, content_id)
            VALUES ((SELECT id FROM cinema.users WHERE login=%s), %s)
            ON CONFLICT (user_id, content_id) DO DELETE
        """, [request.user.username, str(content_id)])
    return JsonResponse({"ok": True})

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