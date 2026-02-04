import logging
from charset_normalizer import from_bytes
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.utils import timezone
from django.db import connection, transaction
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from accounts.forms import CustomPasswordChangeForm, ForgotPasswordForm, ForgotPasswordResetForm, PasswordResetCodeForm, PasswordResetConfirmForm
from catalog.models import CinemaUser, UserSubscription
from cinemaapp import services
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.template.loader import render_to_string
import re

from .models import PasswordResetCode, PasswordResetToken, Profile

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
    return s

def signin(request):
    """
    Логин по логину/почте/телефону + подробные сообщения об ошибках.
    """
    if request.method == "POST":
        login_or_email_or_phone = request.POST.get("login", "").strip()
        password = request.POST.get("password", "")

        if not login_or_email_or_phone:
            messages.error(request, "Укажите логин, e-mail или телефон.")
            return render(request, "accounts/auth/signin.html")
        if not password:
            messages.error(request, "Введите пароль.")
            return render(request, "accounts/auth/signin.html")

        username = _resolve_username(login_or_email_or_phone)
        if not username:
            messages.error(request, "Пользователь не найден.")
            return render(request, "accounts/auth/signin.html")

        user = authenticate(request, username=username, password=password)
        if user is None:
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
            return render(request, "accounts/auth/signin.html")

        if not user.is_active:
            messages.error(request, "Аккаунт отключён. Обратитесь в поддержку.")
            return render(request, "accounts/auth/signin.html")

        login(request, user)
        messages.success(request, "Вы вошли.")
        return redirect(request.GET.get("next") or "main")

    return render(request, "accounts/auth/signin.html")

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

        if not login_val:
            messages.error(request, "Укажите логин.")
            return render(request, "accounts/auth/signup.html")
        if not LOGIN_RE.match(login_val):
            messages.error(request, "Логин 5–32 символа: латинские буквы, цифры, точки, подчёркивания и дефисы.")
            return render(request, "accounts/auth/signup.html")

        if not email:
            messages.error(request, "Укажите e-mail.")
            return render(request, "accounts/auth/signup.html")
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Некорректный e-mail.")
            return render(request, "accounts/auth/signup.html")

  
        if phone and not PHONE_RE.match(phone):
            messages.error(request, "Телефон в формате +79991234567 (10–15 цифр).")
            return render(request, "accounts/auth/signup.html")

        password_errors = []
        if len(password) < 8:
            password_errors.append("минимум 8 символов")
        if not re.search(r"[A-Z]", password):
            password_errors.append("хотя бы одна заглавная буква")
        if not re.search(r"\d", password):
            password_errors.append("хотя бы одна цифра")
        if password_errors:
            messages.error(request, "Пароль слишком простой: " + ", ".join(password_errors) + ".")
            return render(request, "accounts/auth/signup.html")

        if password != password2:
            messages.error(request, "Пароли не совпадают.")
            return render(request, "accounts/auth/signup.html")

        if User.objects.filter(username__iexact=login_val).exists():
            messages.error(request, "Такой логин уже занят.")
            return render(request, "accounts/auth/signup.html")
        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, "Такой e-mail уже используется.")
            return render(request, "accounts/auth/signup.html")

        with transaction.atomic():
            user = User.objects.create_user(
                username=login_val, email=email, password=password, is_active=True
            )
            prof, _ = Profile.objects.get_or_create(user=user)
            if phone:
                prof.phone = phone
                prof.save(update_fields=["phone"])

            password_hash = user.password

            with connection.cursor() as cur:
                cur.execute("""
                    INSERT INTO cinema.users (login, email, password_hash, is_active)
                    VALUES (%s, %s, %s, TRUE)
                    ON CONFLICT (login) DO UPDATE SET
                        email = EXCLUDED.email,
                        password_hash = EXCLUDED.password_hash,
                        is_active = EXCLUDED.is_active,
                        updated_at = NOW()
                """, [login_val, email, password_hash])
        
        messages.success(request, "Регистрация выполнена. Теперь войдите в аккаунт.")
        return redirect("login")

    return render(request, "accounts/auth/signup.html")

@login_required
def profile(request):
    user = request.user
    errors = {}

    active_subscription = None
    try:
        cinema_user = CinemaUser.objects.get(login=user.username)
        active_subscription = UserSubscription.get_current_active_subscription(cinema_user)
    except CinemaUser.DoesNotExist:
        active_subscription = None

    if request.method == "POST":
        new_login = (request.POST.get("username") or "").strip()
        new_email = (request.POST.get("email") or "").strip()
        new_phone = (request.POST.get("phone") or "").strip()

        if not new_login:
            errors["username"] = "Укажите логин."
        elif not LOGIN_RE.match(new_login):
            errors["username"] = "Логин 5–32: латиница, цифры, . _ -"
        elif new_login.lower() != user.username.lower() and \
             User.objects.filter(username__iexact=new_login).exists():
            errors["username"] = "Такой логин уже занят."

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

        if new_phone and not PHONE_RE.match(new_phone):
            errors["phone"] = "Телефон в формате +79991234567 (10–15 цифр)."

        if errors:
            messages.error(request, "Проверьте поля формы.")
            ctx = {
                "form_username": new_login,
                "form_email": new_email,
                "form_phone": new_phone,
                "field_errors": errors,
                "subscription": active_subscription(user.email),
            }
            return render(request, "accounts/profile/profile.html", ctx)

        old_login = user.username
        with transaction.atomic():
            user.username = new_login
            user.email = new_email
            user.save(update_fields=["username", "email"])
            
            prof, _ = Profile.objects.get_or_create(user=user)
            prof.phone = new_phone
            prof.save(update_fields=["phone"])
            
            with connection.cursor() as cur:
                cur.execute("""
                    UPDATE cinema.users
                    SET login = %s,
                        email = %s,
                        updated_at = NOW()
                    WHERE login = %s
                """, [new_login, new_email, old_login])
                
                if cur.rowcount == 0:
                    password_hash = user.password
                    cur.execute("""
                        INSERT INTO cinema.users (login, email, password_hash, is_active)
                        VALUES (%s, %s, %s, TRUE)
                        ON CONFLICT (login) DO NOTHING
                    """, [new_login, new_email, password_hash])
        
        messages.success(request, "Профиль обновлён.")
        return redirect("profile")

    ctx = {
        "form_username": user.username,
        "form_email": user.email,
        "form_phone": getattr(getattr(user, "profile", None), "phone", "") or "",
        "subscription": active_subscription,
        "field_errors": {},
        "now": timezone.now(),
    }
    return render(request, "accounts/profile/profile.html", ctx)


@login_required
def password_change(request):
    """Смена пароля (требуется старый пароль) - используется когда пользователь знает пароль"""
    if request.method == 'POST':
        form = CustomPasswordChangeForm(request.POST)
        
        if form.is_valid():
            old_password = form.cleaned_data['old_password']
            new_password1 = form.cleaned_data['new_password1']
            new_password2 = form.cleaned_data['new_password2']
            
            if not request.user.check_password(old_password):
                messages.error(request, 'Неверный текущий пароль.')
                return render(request, "accounts/password/reset/password_change.html", {'form': form})
            
            if new_password1 != new_password2:
                messages.error(request, 'Новые пароли не совпадают.')
                return render(request, "accounts/password/reset/password_change.html", {'form': form})
            
            password_errors = []
            if len(new_password1) < 8:
                password_errors.append("минимум 8 символов")
            if not re.search(r"[A-Z]", new_password1):
                password_errors.append("хотя бы одна заглавная буква")
            if not re.search(r"\d", new_password1):
                password_errors.append("хотя бы одна цифра")
            if password_errors:
                messages.error(request, "Пароль слишком простой: " + ", ".join(password_errors) + ".")
                return render(request, "accounts/password/reset/password_change.html", {'form': form})

            request.user.set_password(new_password1)
            request.user.save()
            
            update_session_auth_hash(request, request.user)

            with connection.cursor() as cur:
                cur.execute("""
                    UPDATE cinema.users 
                    SET password_hash = %s, updated_at = NOW()
                    WHERE login = %s
                """, [request.user.password, request.user.username])
            
            try:
                subject = 'Пароль изменен'
                message = render_to_string('accounts/password/reset/emails/password_change_complete_email.html', {
                    'user': request.user,
                    'site_name': 'Киновечер',
                    'changed_at': timezone.now(),
                    'ip_address': request.META.get('REMOTE_ADDR', 'неизвестен')
                })
                
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [request.user.email],
                    html_message=message,
                    fail_silently=True
                )
                
                messages.success(request, 
                    'Пароль успешно изменен! На вашу почту отправлено уведомление.')
                    
            except Exception as e:
                logging.error(f"Failed to send password change email: {e}")
                messages.success(request, 'Пароль успешно изменен!')
            
            return redirect('profile')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = CustomPasswordChangeForm()
    
    return render(request, "accounts/password/reset/password_change.html", {'form': form})

@login_required
def password_reset_request(request):
    """Шаг 1: Запрос сброса пароля - отправка кода на email пользователя"""
    if request.method == 'POST' and 'send_code' in request.POST:
        user = request.user
        email = user.email
        
        if not email:
            messages.error(request, 'У вашего аккаунта не указан email.')
            return redirect('profile')
        
        code = PasswordResetCode.generate_code(user.id, email)
        
        subject = 'Код для сброса пароля на Киновечер'
        message = render_to_string('accounts/password/reset/emails/password_reset_code_email.html', {
            'user': user,
            'code': code,
            'site_name': 'Киновечер',
            'expiry_minutes': 30
        })
        
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                html_message=message,
                fail_silently=False
            )
            
            request.session['reset_code_sent'] = True
            request.session['reset_email'] = email
            request.session['reset_user_id'] = str(user.id)
            
            messages.success(request, 
                f'6-значный код отправлен на {email}. '
                f'Проверьте вашу почту (включая папку "Спам").')
            
            logging.info(f"Password reset code sent to {email}")
            
        except Exception as e:
            logging.error(f"Failed to send reset code email: {e}")
            messages.error(request, 
                f'Ошибка при отправке email: {e}. '
                f'Пожалуйста, попробуйте позже.')
    
    elif request.method == 'POST' and 'verify_code' in request.POST:
        form = PasswordResetCodeForm(request.POST)
        
        if form.is_valid():
            code = form.cleaned_data['code']
            email = request.session.get('reset_email')
            user_id = request.session.get('reset_user_id')
            
            if not email or not user_id:
                messages.error(request, 'Сессия истекла. Пожалуйста, запросите код заново.')
                return redirect('password_reset_request')
            
            if PasswordResetCode.verify_code(user_id, email, code):
                messages.success(request, 'Код подтвержден. Теперь установите новый пароль.')
                request.session['code_verified'] = True
                return redirect('password_reset_confirm')
            else:
                messages.error(request, 'Неверный код. Попробуйте еще раз.')
        else:
            for error in form.errors.get('code', []):
                messages.error(request, error)
    

    form = PasswordResetCodeForm() if request.session.get('reset_code_sent') else None
    
    return render(request, "accounts/password/reset/password_reset_request.html", {
        'form': form,
        'code_sent': request.session.get('reset_code_sent', False),
        'user_email': request.user.email if request.user.is_authenticated else None
    })

def password_reset_code(request):
    """Шаг 2: Ввод 6-значного кода"""

    if 'reset_email' not in request.session:
        messages.error(request, 'Пожалуйста, сначала запросите код сброса пароля.')
        return redirect('password_reset_request')
    
    email = request.session['reset_email']
    user_id = request.session['reset_user_id']
    
    if request.method == 'POST':
        form = PasswordResetCodeForm(request.POST)
        
        if form.is_valid():
            code = form.cleaned_data['code']
            

            if PasswordResetCode.verify_code(user_id, email, code):

                messages.success(request, 'Код подтвержден. Теперь установите новый пароль.')
                return redirect('password_reset_confirm')
            else:
                messages.error(request, 'Неверный код. Попробуйте еще раз или запросите новый код.')
        else:
            for error in form.errors.get('code', []):
                messages.error(request, error)
    else:
        form = PasswordResetCodeForm()
    
    return render(request, 'accounts/password/reset/password_reset_code.html', {
        'form': form,
        'email': email
    })

def password_reset_confirm(request):
    """Шаг 2: Установка нового пароля после проверки кода"""
    if not request.session.get('code_verified'):
        messages.error(request, 'Пожалуйста, сначала подтвердите код.')
        return redirect('password_reset_request')
    
    user_id = request.session.get('reset_user_id')
    email = request.session.get('reset_email')
    
    try:
        user = User.objects.get(id=user_id, email__iexact=email)
    except User.DoesNotExist:
        messages.error(request, 'Пользователь не найден.')
        return redirect('password_reset_request')
    
    if request.method == 'POST':
        form = PasswordResetConfirmForm(request.POST)
        
        if form.is_valid():
            new_password1 = form.cleaned_data['new_password1']
            new_password2 = form.cleaned_data['new_password2']
            
            if new_password1 != new_password2:
                messages.error(request, 'Пароли не совпадают.')
                return render(request, "accounts/password/reset/password_reset_confirm.html", {'form': form})

            password_errors = []
            if len(new_password1) < 8:
                password_errors.append("минимум 8 символов")
            if not re.search(r"[A-Z]", new_password1):
                password_errors.append("хотя бы одна заглавная буква")
            if not re.search(r"\d", new_password1):
                password_errors.append("хотя бы одна цифра")
            if password_errors:
                messages.error(request, "Пароль слишком простой: " + ", ".join(password_errors) + ".")
                return render(request, "accounts/password/reset/password_reset_confirm.html", {'form': form})

            user.set_password(new_password1)
            user.save()

            with connection.cursor() as cur:
                cur.execute("""
                    UPDATE cinema.users 
                    SET password_hash = %s, updated_at = NOW()
                    WHERE login = %s
                """, [user.password, user.username])
            

            try:
                subject = 'Пароль сброшен'
                message = render_to_string('accounts/password/reset/emails/password_reset_complete_email.html', {
                    'user': user,
                    'site_name': 'Киновечер',
                    'changed_at': timezone.now(),
                    'ip_address': request.META.get('REMOTE_ADDR', 'неизвестен')
                })
                
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    html_message=message,
                    fail_silently=True
                )
                
            except Exception as e:
                logging.error(f"Failed to send reset complete email: {e}")
            

            for key in ['reset_code_sent', 'reset_email', 'reset_user_id', 'code_verified']:
                if key in request.session:
                    del request.session[key]
            
            messages.success(request, 
                'Пароль успешно изменен! Теперь войдите с новым паролем.')
            return redirect('login')
        
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = PasswordResetConfirmForm()
    
    return render(request, "accounts/password/reset/password_reset_confirm.html", {'form': form})

@login_required
def account_delete_request(request):
    """Запрос на удаление аккаунта (отправка подтверждения на email)"""
    if request.method == 'POST':

        password = request.POST.get('password', '')
        
        if not request.user.check_password(password):
            messages.error(request, 'Неверный пароль.')
            return render(request, "accounts/profile/delete/account_delete_request.html")
        

        token = default_token_generator.make_token(request.user)
        uid = urlsafe_base64_encode(force_bytes(request.user.pk))

        confirm_url = request.build_absolute_uri(
            f'/accounts/account/delete/confirm/{uid}/{token}/'
        )

        subject = 'Подтверждение удаления аккаунта на сайте Киновечер'
        message = render_to_string('accounts/profile/emails/account_delete_email.html', {
            'user': request.user,
            'confirm_url': confirm_url,
            'site_name': 'Киновечер',
            'expiry_hours': 24
        })
        
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [request.user.email],
                html_message=message,
                fail_silently=False
            )
            messages.success(request, 
                f'Ссылка для подтверждения удаления аккаунта отправлена на {request.user.email}. '
                f'Проверьте вашу почту (включая папку "Спам").')
            
            import logging
            logger = logging.getLogger('accounts')
            logger.info(f"Delete confirmation email sent to {request.user.email}")
            
        except Exception as e:
            logger.error(f"Failed to send delete confirmation email: {e}")
            messages.error(request, 
                f'Ошибка при отправке email: {e}. '
                f'Пожалуйста, обратитесь в поддержку.')
        
        return redirect('profile')
    
    return render(request, "accounts/profile/delete/account_delete_request.html")

def account_delete_confirm(request, uidb64, token):
    """Подтверждение удаления аккаунта"""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    
    if user is None:
        messages.error(request, 'Недействительная ссылка для удаления аккаунта.')
        return redirect('main')
    
    if not default_token_generator.check_token(user, token):
        messages.error(request, 'Ссылка для подтверждения удаления недействительна или устарела.')
        return redirect('profile')
    
    if request.method == 'POST':
        confirm_text = request.POST.get('confirm_text', '').strip()
        if confirm_text != 'УДАЛИТЬ':
            messages.error(request, 'Введите слово "УДАЛИТЬ" для подтверждения удаления.')
            return render(request, 'accounts/profile/delete/account_delete_confirm.html', {'user': user})

        password = request.POST.get('password', '')
        if not user.check_password(password):
            messages.error(request, 'Неверный пароль.')
            return render(request, 'accounts/profile/delete/account_delete_confirm.html', {'user': user})
        
        user_email = user.email
        username = user.username
        
        with connection.cursor() as cur:
            cur.execute("DELETE FROM cinema.users WHERE login = %s", [username])
        
        user.delete()
        
        if request.user.is_authenticated and request.user.id == int(uid):
            logout(request)

        try:
            subject = 'Ваш аккаунт на Киновечер удален'
            message = render_to_string('accounts/profile/emails/account_deleted_email.html', {
                'email': user_email,
                'site_name': 'Киновечер',
                'deleted_at': timezone.now()
            })
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user_email],
                html_message=message,
                fail_silently=True
            )
            
            messages.success(request, 
                f'Ваш аккаунт успешно удален. '
                f'На адрес {user_email} отправлено подтверждение удаления.')
                
        except Exception as e:
            logging.error(f"Failed to send deletion confirmation email: {e}")
            messages.success(request, 'Ваш аккаунт успешно удален.')
        
        return redirect('main')
    
    return render(request, 'accounts/profile/delete/account_delete_confirm.html', {'user': user})

def signout(request):
    logout(request)
    messages.success(request, "Вы вышли из аккаунта.")
    return redirect("login")

def forgot_password_request(request):
    """Запрос сброса пароля для неавторизованных пользователей"""
    if request.user.is_authenticated:
        messages.info(request, 'Вы уже авторизованы. Для смены пароля используйте профиль.')
        return redirect('password_reset_request')
    
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        
        if form.is_valid():
            email = form.cleaned_data['email']

            try:
                user = User.objects.get(email__iexact=email)
                
                token = PasswordResetToken.create_token(user.id, email)
                
                reset_url = request.build_absolute_uri(
                    f'/accounts/password/forgot/reset/{token}/'
                )
                
                subject = 'Сброс пароля на сайте Киновечер'
                message = render_to_string('accounts/password/forgot/emails/forgot_password_email.html', {
                    'user': user,
                    'reset_url': reset_url,
                    'site_name': 'Киновечер',
                    'expiry_minutes': 5
                })
                
                try:
                    send_mail(
                        subject,
                        message,
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        html_message=message,
                        fail_silently=False
                    )
                
                    messages.success(request, 
                        'Если email существует в нашей системе, '
                        'на него отправлена ссылка для сброса пароля. '
                        'Проверьте вашу почту (включая папку "Спам"). '
                        'Ссылка действительна 5 минут.')
                    
                    logging.info(f"Forgot password email sent to {email}")
                    
                    return redirect('login')
                    
                except Exception as e:
                    logging.error(f"Failed to send forgot password email: {e}")
                    messages.error(request, 
                        f'Ошибка при отправке email: {e}. '
                        f'Пожалуйста, попробуйте позже.')
                        
            except User.DoesNotExist:
                messages.success(request, 
                    'Если email существует в нашей системе, '
                    'на него отправлена ссылка для сброса пароля. '
                    'Проверьте вашу почту (включая папку "Спам"). '
                    'Ссылка действительна 5 минут.')
                return redirect('login')
    else:
        form = ForgotPasswordForm()
    
    return render(request, "accounts/password/forgot/forgot_password_request.html", {'form': form})

def forgot_password_reset(request, token):
    """Страница сброса пароля по токену (для неавторизованных)"""
    token_data = PasswordResetToken.get_token_data(token)
    
    if not token_data:
        messages.error(request, 
            'Ссылка для сброса пароля недействительна или истекла. '
            'Пожалуйста, запросите новую ссылку.')
        return redirect('forgot_password_request')
    

    try:
        user = User.objects.get(id=token_data['user_id'], email__iexact=token_data['email'])
    except User.DoesNotExist:
        messages.error(request, 'Пользователь не найден.')
        return redirect('forgot_password_request')
    
    if request.method == 'POST':
        form = ForgotPasswordResetForm(request.POST)
        
        if form.is_valid():
            new_password1 = form.cleaned_data['new_password1']
            new_password2 = form.cleaned_data['new_password2']
            

            if new_password1 != new_password2:
                messages.error(request, 'Пароли не совпадают.')
                return render(request, "accounts/password/forgot/forgot_password_reset.html", {
                    'form': form,
                    'token': token
                })
            
            password_errors = []
            if len(new_password1) < 8:
                password_errors.append("минимум 8 символов")
            if not re.search(r"[A-Z]", new_password1):
                password_errors.append("хотя бы одна заглавная буква")
            if not re.search(r"\d", new_password1):
                password_errors.append("хотя бы одна цифра")
            if password_errors:
                messages.error(request, "Пароль слишком простой: " + ", ".join(password_errors) + ".")
                return render(request, "accounts/password/forgot/forgot_password_reset.html", {
                    'form': form,
                    'token': token
                })
            
            user.set_password(new_password1)
            user.save()
            
            with connection.cursor() as cur:
                cur.execute("""
                    UPDATE cinema.users 
                    SET password_hash = %s, updated_at = NOW()
                    WHERE login = %s
                """, [user.password, user.username])
            
            PasswordResetToken.delete_token(token)
            
            try:
                subject = 'Пароль успешно сброшен'
                message = render_to_string('accounts/password/forgot/emails/forgot_password_complete_email.html', {
                    'user': user,
                    'site_name': 'Киновечер',
                    'changed_at': timezone.now(),
                    'ip_address': request.META.get('REMOTE_ADDR', 'неизвестен')
                })
                
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    html_message=message,
                    fail_silently=True
                )
                
            except Exception as e:
                logging.error(f"Failed to send forgot password complete email: {e}")
            
            messages.success(request, 
                'Пароль успешно изменен! Теперь войдите с новым паролем.')
            return redirect('login')
        
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = ForgotPasswordResetForm()
    
    return render(request, "accounts/password/forgot/forgot_password_reset.html", {
        'form': form,
        'token': token,
        'email': token_data['email']
    })