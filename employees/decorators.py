from django.shortcuts import redirect
from django.contrib import messages

def employee_required(view_func):
    """
    Декоратор для проверки, что пользователь - сотрудник.
    Используется для страниц сотрудников.
    """
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Требуется авторизация')
            return redirect('employee_login')
        
        if not request.session.get('is_employee'):
            messages.error(request, 'Эта страница только для сотрудников')
            return redirect('home')
        
        return view_func(request, *args, **kwargs)
    return wrapper

def check_employee_role(required_role):
    """
    Декоратор для проверки конкретной роли сотрудника.
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('employee_login')
            
            if not request.session.get('is_employee'):
                return redirect('home')
            
            roles = request.session.get('employee_roles', [])
            
            if required_role not in roles:
                messages.error(request, f'Требуется роль: {required_role}')
                return redirect('no_role_panel')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator