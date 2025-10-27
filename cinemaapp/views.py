from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_POST
from .models import Favorite, Content
from django.shortcuts import render
from django.contrib.auth import get_user_model, get_user as auth_get_user

User = get_user_model()

def _get_content_or_404(pk):
    try:
        return Content.objects.get(pk=pk)
    except Content.DoesNotExist:
        raise Http404
    
def _current_user_id(request) -> str:
    uid = request.session.get('_auth_user_id')
    if not uid:
        raise Http404('No auth user in session')
    return uid

def _resolve_user(request):
    u = getattr(request, 'user', None)

    if hasattr(u, 'pk'):
        return u

    if isinstance(u, str):
        return User.objects.get(username=u)

    uid = request.session.get('_auth_user_id')
    if uid:
        try:
            return User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError):
            pass

    raise Http404('Не удалось определить пользователя')

@login_required
def my_favorites(request):
    items = (Content.objects
             .filter(favorited_by__user=request.user)
             .select_related('cover_image')
             .order_by('-favorited_by__created_at'))
    return render(request, 'account/my_favorites.html', {'items': items})

@login_required
def content_favorite_check(request, pk):
    user = _resolve_user(request)
    content = _get_content_or_404(pk)
    is_fav = Favorite.objects.filter(user=user, content=content).exists()
    return JsonResponse({'is_favorite': is_fav})

@login_required
@require_POST
def content_favorite_toggle(request, pk):
    user = _resolve_user(request)
    content = _get_content_or_404(pk)

    action = (request.POST.get('action') or '').lower()
    if action == 'add':
        Favorite.objects.get_or_create(user=user, content=content)
        is_fav = True
    elif action == 'remove':
        Favorite.objects.filter(user=user, content=content).delete()
        is_fav = False
    else:
        obj, created = Favorite.objects.get_or_create(user=user, content=content)
        if created:
            is_fav = True
        else:
            obj.delete()
            is_fav = False

    return JsonResponse({'ok': True, 'is_favorite': is_fav})