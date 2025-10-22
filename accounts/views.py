from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.db import connection, transaction
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
import re

from .models import Profile

LOGIN_RE = re.compile(r"^[A-Za-z0-9._-]{5,32}$")
PHONE_RE = re.compile(r"^\+?\d{10,15}$")

def _resolve_username(s: str) -> str | None:
    s = (s or "").strip()
    if not s: return None
    if "@" in s:
        u = User.objects.filter(email__iexact=s).first()
        return u.username if u else None
    if PHONE_RE.match(s):
        p = Profile.objects.filter(phone=s).select_related("user").first()
        return p.user.username if p else None
    return s  # предполагает логин

def signin(request):
    """
    Логин по логину/почте/телефону + подробные сообщения об ошибках.
    """
    if request.method == "POST":
        login_or_email_or_phone = request.POST.get("login", "").strip()
        password = request.POST.get("password", "")

        # базовые проверки
        if not login_or_email_or_phone:
            messages.error(request, "Укажите логин, e-mail или телефон.")
            return render(request, "accounts/signin.html")
        if not password:
            messages.error(request, "Введите пароль.")
            return render(request, "accounts/signin.html")

        # нормализация логин
        username = _resolve_username(login_or_email_or_phone)
        if not username:
            messages.error(request, "Пользователь не найден.")
            return render(request, "accounts/signin.html")

        # попытка аутентификации
        user = authenticate(request, username=username, password=password)
        if user is None:
            # подсказки по паролю
            hints = []
            if len(password) < 8:
                hints.append("минимум 8 символов")
            if not re.search(r"[A-Z]", password):
                hints.append("хотя бы одна заглавная буква")
            if not re.search(r"\d", password):
                hints.append("хотя бы одна цифра")
            if hints:
                messages.error(request, "Неверный логин или пароль. Требования к паролю: " + ", ".join(hints) + ".")
            else:
                messages.error(request, "Неверный логин или пароль.")
            return render(request, "accounts/signin.html")

        if not user.is_active:
            messages.error(request, "Аккаунт отключён. Обратитесь в поддержку.")
            return render(request, "accounts/signin.html")

        login(request, user)
        messages.success(request, "Вы вошли.")
        return redirect(request.GET.get("next") or "main")

    return render(request, "accounts/signin.html")

def signup(request):
    """
    Регистрация с детальной валидацией полей и понятными ошибками.
    Также создаёт запись в cinema.users (ON CONFLICT DO NOTHING).
    """
    if request.method == "POST":
        login_val = request.POST.get("login", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")
        password2 = request.POST.get("password2", "")

        # --- валидация логина
        if not login_val:
            messages.error(request, "Укажите логин.")
            return render(request, "accounts/signup.html")
        if not LOGIN_RE.match(login_val):
            messages.error(request, "Логин 5–32 символа: латинские буквы, цифры, точки, подчёркивания и дефисы.")
            return render(request, "accounts/signup.html")

        # --- валидация e-mail
        if not email:
            messages.error(request, "Укажите e-mail.")
            return render(request, "accounts/signup.html")
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Некорректный e-mail.")
            return render(request, "accounts/signup.html")

        # --- валидация телефона
        if phone and not PHONE_RE.match(phone):
            messages.error(request, "Телефон в формате +79991234567 (10–15 цифр).")
            return render(request, "accounts/signup.html")

        # --- пароль
        password_errors = []
        if len(password) < 8:
            password_errors.append("минимум 8 символов")
        if not re.search(r"[A-Z]", password):
            password_errors.append("хотя бы одна заглавная буква")
        if not re.search(r"\d", password):
            password_errors.append("хотя бы одна цифра")
        if password_errors:
            messages.error(request, "Пароль слишком простой: " + ", ".join(password_errors) + ".")
            return render(request, "accounts/signup.html")

        if password != password2:
            messages.error(request, "Пароли не совпадают.")
            return render(request, "accounts/signup.html")

        # --- уникальность
        if User.objects.filter(username__iexact=login_val).exists():
            messages.error(request, "Такой логин уже занят.")
            return render(request, "accounts/signup.html")
        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, "Такой e-mail уже используется.")
            return render(request, "accounts/signup.html")

        # --- создание пользователя + синхронизация в cinema.users
        with transaction.atomic():
            user = User.objects.create_user(
                username=login_val, email=email, password=password, is_active=True
            )
            prof, _ = Profile.objects.get_or_create(user=user)
            if phone:
                prof.phone = phone
                prof.save(update_fields=["phone"])

            # запись в доменную таблицу
            with connection.cursor() as cur:
                cur.execute("""
                    INSERT INTO cinema.users (login, email, password_hash, is_active)
                    VALUES (%s, %s, %s, TRUE)
                    ON CONFLICT (login) DO NOTHING
                """, [login_val, email, '$argon2id$v=19$m=65536,t=2,p=1$X$X'])

        messages.success(request, "Регистрация выполнена. Теперь войдите в аккаунт.")
        return redirect("login")

    return render(request, "accounts/signup.html")

@login_required
def profile(request):
    user = request.user
    errors = {}

    if request.method == "POST":
        new_login = (request.POST.get("username") or "").strip()
        new_email = (request.POST.get("email") or "").strip()
        new_phone = (request.POST.get("phone") or "").strip()

        # ---- ВАЛИДАЦИЯ ----
        # логин
        if not new_login:
            errors["username"] = "Укажите логин."
        elif not LOGIN_RE.match(new_login):
            errors["username"] = "Логин 5–32: латиница, цифры, . _ -"
        elif new_login.lower() != user.username.lower() and \
             User.objects.filter(username__iexact=new_login).exists():
            errors["username"] = "Такой логин уже занят."

        # email
        if not new_email:
            errors["email"] = "Укажите e-mail."
        else:
            try:
                validate_email(new_email)
            except ValidationError:
                errors["email"] = "Некорректный e-mail."
        if "email" not in errors and \
           User.objects.exclude(pk=user.pk).filter(email__iexact=new_email).exists():
            errors["email"] = "Этот e-mail уже используется."

        # телефон (необязателен)
        if new_phone and not PHONE_RE.match(new_phone):
            errors["phone"] = "Телефон в формате +79991234567 (10–15 цифр)."

        if errors:
            # общая шапка + прокинем введённые значения обратно
            messages.error(request, "Проверьте поля формы.")
            ctx = {
                "form_username": new_login,
                "form_email": new_email,
                "form_phone": new_phone,
                "field_errors": errors,
            }
            return render(request, "accounts/profile.html", ctx)

        # ---- СОХРАНЕНИЕ ----
        old_login = user.username
        with transaction.atomic():
            # обновляем auth_user
            user.username = new_login
            user.email = new_email
            user.save(update_fields=["username", "email"])

            # профиль (телефон)
            prof, _ = Profile.objects.get_or_create(user=user)
            prof.phone = new_phone
            prof.save(update_fields=["phone"])

            # синхронизация с cinema.users
            with connection.cursor() as cur:
                # если запись есть — обновим; если нет — создадим
                cur.execute("""
                    UPDATE cinema.users
                       SET login = %s,
                           email = %s
                     WHERE login = %s
                """, [new_login, new_email, old_login])
                if cur.rowcount == 0:
                    cur.execute("""
                        INSERT INTO cinema.users (login, email, password_hash, is_active)
                        VALUES (%s, %s, %s, TRUE)
                        ON CONFLICT (login) DO NOTHING
                    """, [new_login, new_email, '$argon2id$v=19$m=65536,t=2,p=1$X$X'])

        messages.success(request, "Профиль обновлён.")
        return redirect("profile")

    # GET — отрисует форму
    ctx = {
        "form_username": user.username,
        "form_email": user.email,
        "form_phone": getattr(getattr(user, "profile", None), "phone", "") or "",
        "field_errors": {},
    }
    return render(request, "accounts/profile.html", ctx)

def signout(request):
    logout(request)
    messages.success(request, "Вы вышли из аккаунта.")
    return redirect("login")