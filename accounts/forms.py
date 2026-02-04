import re
from django import forms
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.core.validators import RegexValidator

LOGIN_RE = re.compile(r"^[A-Za-z0-9._-]{5,32}$")

class CustomPasswordChangeForm(forms.Form):
    """Форма для смены пароля (старый + новый пароль)"""
    old_password = forms.CharField(
        label="Текущий пароль",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Введите текущий пароль'})
    )
    new_password1 = forms.CharField(
        label="Новый пароль",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Введите новый пароль'}),
        help_text="Минимум 8 символов, хотя бы одна заглавная буква и цифра"
    )
    new_password2 = forms.CharField(
        label="Подтверждение нового пароля",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Повторите новый пароль'})
    )

class PasswordResetCodeForm(forms.Form):
    """Форма для ввода 6-значного кода"""
    code = forms.CharField(
        label="6-значный код",
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Введите 6-значный код из письма',
            'maxlength': '6',
            'minlength': '6',
            'autocomplete': 'off'
        }),
        validators=[
            RegexValidator(regex='^[0-9]{6}$', message='Код должен содержать ровно 6 цифр')
        ]
    )

class PasswordResetConfirmForm(forms.Form):
    """Форма для установки нового пароля после проверки кода"""
    new_password1 = forms.CharField(
        label="Новый пароль",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Введите новый пароль'}),
        help_text="Минимум 8 символов, хотя бы одна заглавная буква и цифра"
    )
    new_password2 = forms.CharField(
        label="Подтверждение нового пароля",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Повторите новый пароль'})
    )

class AccountDeleteForm(forms.Form):
    """Форма для подтверждения удаления аккаунта"""
    confirm_text = forms.CharField(
        label='Введите "УДАЛИТЬ" для подтверждения',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'УДАЛИТЬ'}),
        validators=[RegexValidator(regex='^УДАЛИТЬ$', message='Введите слово УДАЛИТЬ для подтверждения')]
    )
    password = forms.CharField(
        label="Ваш текущий пароль",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )

class ForgotPasswordForm(forms.Form):
    """Форма для запроса сброса пароля (когда пользователь не авторизован)"""
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Введите email вашего аккаунта',
            'autocomplete': 'email'
        }),
        help_text="На этот email мы отправим ссылку для сброса пароля"
    )

class ForgotPasswordResetForm(forms.Form):
    """Форма для установки нового пароля после перехода по ссылке"""
    new_password1 = forms.CharField(
        label="Новый пароль",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Введите новый пароль',
            'autocomplete': 'new-password'
        }),
        help_text="Минимум 8 символов, хотя бы одна заглавная буква и цифра"
    )
    new_password2 = forms.CharField(
        label="Подтверждение нового пароля",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Повторите новый пароль',
            'autocomplete': 'new-password'
        })
    )