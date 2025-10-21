from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect

from .models import Profile

def _find_username_by_login(login_str: str) -> str | None:
    """Вернёт username по вводу (логин/почта/телефон)."""
    s = (login_str or "").strip()
    if not s:
        return None
    # почта?
    if "@" in s:
        u = User.objects.filter(email__iexact=s).first()
        return u.username if u else None
    # телефон?
    prof = Profile.objects.filter(phone=s).select_related("user").first()
    if prof:
        return prof.user.username
    # иначе это username
    return s

def login_view(request):
    if request.method == 'POST':
        login_input = request.POST.get('username')
        password = request.POST.get('password')

        username = _find_username_by_login(login_input)
        if not username:
            messages.error(request, 'Пользователь не найден.')
            return render(request, 'accounts/login.html')

        user = authenticate(request, username=username, password=password)
        if user is None:
            messages.error(request, 'Неверный логин/почта/телефон или пароль.')
            return render(request, 'accounts/login.html')

        if not user.is_active:
            messages.error(request, 'Аккаунт не активен.')
            return render(request, 'accounts/login.html')

        login(request, user)
        return redirect('main')

    return render(request, 'accounts/login.html')

from django.contrib.auth import logout

def logout_view(request):
    if request.method == 'POST':
        logout(request)
        return redirect('main')
    return redirect('profile')

def register_view(request):
    """Регистрация (почта или телефон)."""
    if request.method == 'POST':
        p1 = request.POST.get('password1')
        p2 = request.POST.get('password2')
        contact = (request.POST.get('contact') or '').strip()

        if not contact:
            messages.error(request, 'Укажите почту или телефон.')
            return render(request, 'accounts/register.html')
        if p1 != p2:
            messages.error(request, 'Пароли не совпадают.')
            return render(request, 'accounts/register.html')

        base_username = contact.split('@')[0] if '@' in contact else contact
        username = base_username
        i = 1
        while User.objects.filter(username=username).exists():
            i += 1
            username = f"{base_username}{i}"

        u = User.objects.create_user(username=username, password=p1)

        if '@' in contact:
            u.email = contact
            u.save()
        else:
            u.save()
            prof, _ = Profile.objects.get_or_create(user=u)
            prof.phone = contact
            prof.save()

        login(request, u)
        return redirect('main')

    return render(request, 'accounts/register.html')


@login_required(login_url='/login/')
def profile_view(request):
    """Просмотр/редактирование профиля."""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()

        if username and username != request.user.username:
            if User.objects.filter(username=username).exclude(id=request.user.id).exists():
                messages.error(request, 'Такой логин уже занят.')
            else:
                request.user.username = username

        request.user.email = email
        request.user.save()

        prof, _ = Profile.objects.get_or_create(user=request.user)
        prof.phone = phone
        prof.save()

        messages.success(request, 'Профиль сохранён.')
        return redirect('profile')

    return render(request, 'accounts/profile.html', {
        'subscription': None, 'purchases': [], 'ratings': [], 'history': [],
        'support_messages': [],
    })