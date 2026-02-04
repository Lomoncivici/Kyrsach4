import logging
from django.db import connection
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.urls import reverse

logger = logging.getLogger(__name__)


def redirect_by_role(request):
    """Редирект сотрудника по ролям"""
    roles = request.session.get('employee_roles', [])
    
    if 'ADMIN' in roles:
        return redirect('admin_panel')
    elif 'ANALYST' in roles:
        return redirect('analytics_panel')
    elif 'SUPPORT' in roles:
        return redirect('support_panel')
    else:
        return redirect('no_role_panel')

def employee_login(request):
    """Вход ТОЛЬКО для сотрудников через EmployeeBackend"""
    
    if request.session.get('is_employee'):
        return redirect_by_role(request)
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        
        logger.info(f"Employee login attempt: {email}")

        user = authenticate(
            request, 
            username=email, 
            password=password,
            backend='employees.backends.EmployeeBackend'
        )
        
        if user is not None:

            if request.session.get('is_employee'):
                login(request, user)
                
                employee_name = request.session.get('employee_name', 'Сотрудник')
                messages.success(request, f'Добро пожаловать, {employee_name}!')
                return redirect_by_role(request)
            else:
                # Если почему-то нет флага is_employee - ошибка
                messages.error(request, 'Ошибка аутентификации сотрудника')
                logger.error(f"Employee auth succeeded but no is_employee flag: {email}")
        else:
            messages.error(request, 'Неверный email или пароль для сотрудника')
    
    return render(request, 'employees/login.html')

def employee_logout(request):
    """Выход для сотрудников"""
    for key in ['is_employee', 'employee_id', 'employee_email', 
                'employee_name', 'employee_roles']:
        if key in request.session:
            del request.session[key]
    
    logout(request)
    messages.success(request, 'Вы вышли из системы сотрудника')
    return redirect('employee_login')


def employee_required(view_func):
    """Декоратор для проверки, что пользователь - сотрудник"""
    def wrapper(request, *args, **kwargs):
        if not request.session.get('is_employee'):
            messages.error(request, 'Требуется авторизация сотрудника')
            return redirect('employee_login')
        return view_func(request, *args, **kwargs)
    return wrapper

def check_employee_role(required_role):
    """Декоратор для проверки конкретной роли сотрудника"""
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if not request.session.get('is_employee'):
                messages.error(request, 'Требуется авторизация сотрудника')
                return redirect('employee_login')
            
            roles = request.session.get('employee_roles', [])
            
            if required_role not in roles:
                messages.error(request, f'У вас нет прав для доступа к этой панели')
                return redirect('no_role_panel')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

@employee_required
@check_employee_role('ADMIN')
def admin_content_list(request):
    """Список всего контента"""
    from django.db import connection
    
    search_query = request.GET.get('search', '').strip()
    content_type = request.GET.get('type')
    free_filter = request.GET.get('free')
    
    query = """
        SELECT 
            c.id::text, 
            c.title, 
            c.type, 
            c.release_year, 
            c.description,
            c.is_free, 
            COALESCE(c.price::text, '0.00') as price, 
            c.created_at,
            ma_cover.url as cover_url,
            STRING_AGG(g.name, ', ') as genres
        FROM cinema.content c
        LEFT JOIN cinema.content_genres cg ON cg.content_id = c.id
        LEFT JOIN cinema.genres g ON g.id = cg.genre_id
        LEFT JOIN cinema.media_assets ma_cover ON ma_cover.id = c.cover_image_id
    """
    
    where_clauses = []
    params = []
    
    if search_query:
        where_clauses.append("(c.title ILIKE %s OR c.description ILIKE %s)")
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    
    if content_type and content_type != 'all':
        where_clauses.append("c.type = %s")
        params.append(content_type)
    
    if free_filter:
        if free_filter == 'true':
            where_clauses.append("c.is_free = true")
        elif free_filter == 'false':
            where_clauses.append("c.is_free = false")
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    query += """
        GROUP BY c.id, c.title, c.type, c.release_year, c.description, 
                 c.is_free, c.price, c.created_at, ma_cover.url
        ORDER BY c.created_at DESC
    """
    
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        
        columns = [col[0] for col in cursor.description]
        content_list = []
        for row in cursor.fetchall():
            content_dict = dict(zip(columns, row))
            content_list.append(content_dict)
    
    return render(request, 'employees/admin/content/admin_content_list.html', {
        'content_list': content_list,
        'employee_name': request.session.get('employee_name'),
        'search_query': search_query,
        'current_type': content_type,
        'current_free': free_filter,
        'total_count': len(content_list),
    })

def create_or_get_media_asset(cursor, url, kind, mime_type):
    """Создает или получает существующий медиа-актив"""
    if not url:
        return None
    
    cursor.execute("""
        SELECT id FROM cinema.media_assets 
        WHERE url = %s AND kind = %s
        LIMIT 1
    """, [url, kind])
    
    result = cursor.fetchone()
    if result:
        return result[0]
    
    cursor.execute("""
        INSERT INTO cinema.media_assets 
        (id, kind, mime_type, url, created_at)
        VALUES (gen_random_uuid(), %s, %s, %s, NOW())
        RETURNING id
    """, [kind, mime_type, url])
    
    return cursor.fetchone()[0]

@employee_required
@check_employee_role('ADMIN')
def admin_content_add(request):
    """Добавление нового контента"""
    from django.db import connection
    from django.contrib import messages
    import decimal
    from decimal import Decimal
    
    def get_mime_type(url, kind):
        """Определяет MIME-тип по URL"""
        if kind == 'video':
            if url.endswith('.mp4'):
                return 'video/mp4'
            elif url.endswith('.webm'):
                return 'video/webm'
            elif url.endswith('.m3u8'):
                return 'application/vnd.apple.mpegurl'
            elif url.endswith('.mpd'):
                return 'application/dash+xml'
            else:
                return 'video/mp4'
        elif kind == 'image':
            if url.endswith('.jpg') or url.endswith('.jpeg'):
                return 'image/jpeg'
            elif url.endswith('.png'):
                return 'image/png'
            else:
                return 'image/jpeg'
        return 'text/html'
    
    if request.method == 'POST':
        try:
            title = request.POST.get('title')
            content_type = request.POST.get('type')
            release_year = request.POST.get('release_year')
            description = request.POST.get('description')
            is_free = request.POST.get('is_free') == 'on'
            price_str = request.POST.get('price', '0')

            video_url = request.POST.get('video_url', '').strip()
            cover_image_url = request.POST.get('cover_image_url', '').strip()
            trailer_url = request.POST.get('trailer_url', '').strip()
            cover_image_wide_url = request.POST.get('cover_image_wide_url', '').strip()

            if content_type == 'movie' and not video_url:
                messages.error(request, 'Для фильма требуется указать URL видео')
                return redirect('admin_content_add')

            try:
                price_str = price_str.replace(',', '.')
                price_decimal = Decimal(price_str)
            except (decimal.InvalidOperation, ValueError, TypeError):
                price_decimal = Decimal('0')
            
            price_decimal = price_decimal.quantize(Decimal('0.01'))
            
            if is_free:
                price_decimal = Decimal('0.00')

            if not is_free and price_decimal <= Decimal('0'):
                messages.error(request, 'Цена платного контента должна быть больше 0')
                return redirect('admin_content_add')
            
            genre_ids = request.POST.getlist('genres')
            
            with connection.cursor() as cursor:

                video_id = None
                cover_image_id = None
                trailer_id = None
                cover_image_wide_id = None
                
                if content_type == 'movie' and video_url:
                    video_id = create_or_get_media_asset(
                        cursor, video_url, 'video', get_mime_type(video_url, 'video')
                    )
                
                if cover_image_url:
                    cover_image_id = create_or_get_media_asset(
                        cursor, cover_image_url, 'image', get_mime_type(cover_image_url, 'image')
                    )
                
                if trailer_url:
                    trailer_id = create_or_get_media_asset(
                        cursor, trailer_url, 'video', get_mime_type(trailer_url, 'video')
                    )
                
                if cover_image_wide_url:
                    cover_image_wide_id = create_or_get_media_asset(
                        cursor, cover_image_wide_url, 'image', get_mime_type(cover_image_wide_url, 'image')
                    )
                

                cursor.execute("""
                    INSERT INTO cinema.content 
                    (id, title, type, release_year, description, 
                     is_free, price, video_id, cover_image_id, 
                     trailer_id, cover_image_wide_id, created_at, updated_at)
                    VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    RETURNING id::text
                """, [
                    title, content_type, release_year, 
                    description, is_free, str(price_decimal), 
                    video_id, cover_image_id, trailer_id, cover_image_wide_id
                ])
                
                content_id = cursor.fetchone()[0]
                
                for genre_id in genre_ids:
                    cursor.execute("""
                        INSERT INTO cinema.content_genres (content_id, genre_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                    """, [content_id, genre_id])
                
                messages.success(request, f'Контент "{title}" успешно добавлен!')
                return redirect('admin_content_list')
                
        except Exception as e:
            messages.error(request, f'Ошибка при добавлении контента: {str(e)}')
            import traceback
            traceback.print_exc()

    with connection.cursor() as cursor:
        cursor.execute("SELECT id::text, name FROM cinema.genres ORDER BY name")
        genres = cursor.fetchall()
    
    return render(request, 'employees/admin/content/add/admin_content_add.html', {
        'genres': genres,
        'employee_name': request.session.get('employee_name'),
    })

def update_or_create_media(cursor, current_id, url, kind):
    """Обновляет или создает медиа-актив"""
    if not url or not url.strip():
        return None
    
    url = url.strip()
    
    if not url.startswith(('http://', 'https://')):
        return None

    if len(url) > 2048:
        logger.warning(f"URL too long: {len(url)} characters")
        return None
    

    if kind == 'video':
        if url.endswith('.mp4'):
            mime_type = 'video/mp4'
        elif url.endswith('.webm'):
            mime_type = 'video/webm'
        elif url.endswith('.m3u8'):
            mime_type = 'application/vnd.apple.mpegurl'
        elif url.endswith('.mpd'):
            mime_type = 'application/dash+xml'
        else:
            mime_type = 'video/mp4'
    else:
        if url.endswith('.jpg') or url.endswith('.jpeg'):
            mime_type = 'image/jpeg'
        elif url.endswith('.png'):
            mime_type = 'image/png'
        else:
            mime_type = 'image/jpeg'
    
    try:

        cursor.execute("""
            INSERT INTO cinema.media_assets 
            (id, kind, mime_type, url, created_at)
            VALUES (gen_random_uuid(), %s, %s, %s, NOW())
            ON CONFLICT (url) DO UPDATE 
            SET mime_type = EXCLUDED.mime_type
            RETURNING id
        """, [kind, mime_type, url])
        
        return cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"Error in update_or_create_media: {e}")
        

        cursor.execute("""
            SELECT id FROM cinema.media_assets 
            WHERE url = %s
            LIMIT 1
        """, [url])
        
        existing = cursor.fetchone()
        return existing[0] if existing else None

def is_valid_url(url):
    """Проверяет валидность URL"""
    if not url or not url.strip():
        return False
    url = url.strip()

    if not url.startswith(('http://', 'https://')):
        return False

    if len(url) > 2048:
        return False
    return True

def sanitize_url(url):
    """Очищает URL от лишних пробелов и проверяет формат"""
    if not url:
        return ''
    url = url.strip()

    if url and not url.startswith(('http://', 'https://')):
        return ''
    return url

@employee_required
@check_employee_role('ADMIN')
def admin_content_edit(request, content_id):
    """Редактирование контента"""
    from django.contrib import messages
    import decimal
    from decimal import Decimal
    
    if request.method == 'POST':
        try:
            title = request.POST.get('title')
            content_type = request.POST.get('type')
            release_year = request.POST.get('release_year')
            description = request.POST.get('description')
            is_free = request.POST.get('is_free') == 'on'
            price_str = request.POST.get('price', '0')
            

            video_url = sanitize_url(request.POST.get('video_url', ''))
            cover_image_url = sanitize_url(request.POST.get('cover_image_url', ''))
            trailer_url = sanitize_url(request.POST.get('trailer_url', ''))
            cover_image_wide_url = sanitize_url(request.POST.get('cover_image_wide_url', ''))

            if content_type == 'movie':
                if not video_url:
                    messages.error(request, 'Для фильма требуется указать URL видео')
                    return redirect('admin_content_edit', content_id=content_id)
                if not is_valid_url(video_url):
                    messages.error(request, 'URL видео должен начинаться с http:// или https://')
                    return redirect('admin_content_edit', content_id=content_id)

            try:
                price_str = price_str.replace(',', '.')
                price_decimal = Decimal(price_str)
            except (decimal.InvalidOperation, ValueError, TypeError):
                price_decimal = Decimal('0')

            price_decimal = price_decimal.quantize(Decimal('0.01'))

            if is_free:
                price_decimal = Decimal('0.00')

            if not is_free and price_decimal <= Decimal('0'):
                messages.error(request, 'Цена платного контента должна быть больше 0')
                return redirect('admin_content_edit', content_id=content_id)
            
            genre_ids = request.POST.getlist('genres')
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT video_id, cover_image_id, trailer_id, cover_image_wide_id
                    FROM cinema.content WHERE id = %s
                """, [content_id])
                result = cursor.fetchone()
                if result:
                    current_video_id, current_cover_id, current_trailer_id, current_wide_id = result
                else:
                    current_video_id = current_cover_id = current_trailer_id = current_wide_id = None

                video_id = None
                cover_image_id = None
                trailer_id = None
                cover_image_wide_id = None
                
                if is_valid_url(video_url):
                    video_id = update_or_create_media(cursor, current_video_id, video_url, 'video')
                
                if is_valid_url(cover_image_url):
                    cover_image_id = update_or_create_media(cursor, current_cover_id, cover_image_url, 'image')
                
                if is_valid_url(trailer_url):
                    trailer_id = update_or_create_media(cursor, current_trailer_id, trailer_url, 'video')
                
                if is_valid_url(cover_image_wide_url):
                    cover_image_wide_id = update_or_create_media(cursor, current_wide_id, cover_image_wide_url, 'image')
                
                if content_type == 'series':
                    video_id = None

                cursor.execute("""
                    UPDATE cinema.content 
                    SET title = %s, type = %s, release_year = %s, 
                        description = %s, is_free = %s, price = %s,
                        video_id = %s, cover_image_id = %s,
                        trailer_id = %s, cover_image_wide_id = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, [title, content_type, release_year, 
                      description, is_free, str(price_decimal),
                      video_id, cover_image_id, trailer_id, cover_image_wide_id,
                      content_id])
                

                cursor.execute("DELETE FROM cinema.content_genres WHERE content_id = %s", [content_id])
                

                for genre_id in genre_ids:
                    cursor.execute("""
                        INSERT INTO cinema.content_genres (content_id, genre_id)
                        VALUES (%s, %s)
                    """, [content_id, genre_id])
                
                messages.success(request, f'Контент "{title}" успешно обновлен!')
                return redirect('admin_content_list')
                
        except Exception as e:
            logger.error(f"Error updating content: {e}")
            messages.error(request, f'Ошибка при обновлении контента: {str(e)}')
    

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                c.id::text, 
                c.title, 
                c.type, 
                c.release_year, 
                c.description, 
                c.is_free, 
                COALESCE(c.price::text, '0.00') as price,
                ma_video.url as video_url,
                ma_cover.url as cover_image_url,
                ma_trailer.url as trailer_url,
                ma_wide.url as cover_image_wide_url
            FROM cinema.content c
            LEFT JOIN cinema.media_assets ma_video ON ma_video.id = c.video_id
            LEFT JOIN cinema.media_assets ma_cover ON ma_cover.id = c.cover_image_id
            LEFT JOIN cinema.media_assets ma_trailer ON ma_trailer.id = c.trailer_id
            LEFT JOIN cinema.media_assets ma_wide ON ma_wide.id = c.cover_image_wide_id
            WHERE c.id = %s
        """, [content_id])
        
        row = cursor.fetchone()
        if row:
            content = list(row)
        else:
            content = None

        cursor.execute("SELECT id::text, name FROM cinema.genres ORDER BY name")
        all_genres = cursor.fetchall()

        cursor.execute("""
            SELECT genre_id::text 
            FROM cinema.content_genres 
            WHERE content_id = %s
        """, [content_id])
        selected_genres = [row[0] for row in cursor.fetchall()]
    
    if not content:
        messages.error(request, 'Контент не найден')
        return redirect('admin_content_list')
    
    context = {
        'content': content,
        'all_genres': all_genres,
        'selected_genres': selected_genres,
        'employee_name': request.session.get('employee_name'),
        'content_id': content_id,

        'video_url': content[7] if content and len(content) > 7 else '',
        'cover_image_url': content[8] if content and len(content) > 8 else '',
        'trailer_url': content[9] if content and len(content) > 9 else '',
        'cover_image_wide_url': content[10] if content and len(content) > 10 else '',
    }
    
    return render(request, 'employees/admin/content/edit/admin_content_edit.html', context)

@employee_required
@check_employee_role('ADMIN')
def admin_content_delete(request, content_id):
    """Удаление контента"""
    from django.db import connection
    
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:

                cursor.execute("SELECT title FROM cinema.content WHERE id = %s", [content_id])
                result = cursor.fetchone()
                
                if result:
                    content_title = result[0]

                    cursor.execute("DELETE FROM cinema.content WHERE id = %s", [content_id])
                    
                    messages.success(request, f'Контент "{content_title}" успешно удален!')
                else:
                    messages.error(request, 'Контент не найден')
        except Exception as e:
            messages.error(request, f'Ошибка при удалении контента: {str(e)}')
    
    return redirect('admin_content_list')

@employee_required
@check_employee_role('ADMIN')
def admin_genres(request):
    """Управление жанрами"""
    from django.db import connection
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            genre_name = request.POST.get('genre_name')
            if genre_name:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO cinema.genres (id, name) 
                            VALUES (gen_random_uuid(), %s)
                            ON CONFLICT (name) DO NOTHING
                        """, [genre_name])
                        messages.success(request, f'Жанр "{genre_name}" добавлен')
                except Exception as e:
                    messages.error(request, f'Ошибка: {str(e)}')
        
        elif action == 'delete':
            genre_id = request.POST.get('genre_id')
            if genre_id:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("DELETE FROM cinema.genres WHERE id = %s", [genre_id])
                        messages.success(request, 'Жанр удален')
                except Exception as e:
                    messages.error(request, f'Ошибка: {str(e)}')
    
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, name FROM cinema.genres ORDER BY name")
        genres = cursor.fetchall()
        
        cursor.execute("""
            SELECT g.name, COUNT(cg.content_id) as usage_count
            FROM cinema.genres g
            LEFT JOIN cinema.content_genres cg ON cg.genre_id = g.id
            GROUP BY g.id, g.name
            ORDER BY usage_count DESC
        """)
        genre_stats = cursor.fetchall()
    
    return render(request, 'employees/admin/content/admin_genres.html', {
        'genres': genres,
        'genre_stats': genre_stats,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_seasons_management(request):
    """Управление сезонами и эпизодами"""
    from django.db import connection
    
    series_id = request.GET.get('series_id')
    
    with connection.cursor() as cursor:

        cursor.execute("""
            SELECT id::text, title, release_year 
            FROM cinema.content 
            WHERE type = 'series' 
            ORDER BY title
        """)
        series_list = cursor.fetchall()
        
        selected_series = None
        seasons = []
        
        if series_id:

            cursor.execute("""
                SELECT id::text, title, release_year, description
                FROM cinema.content 
                WHERE id = %s AND type = 'series'
            """, [series_id])
            selected_series = cursor.fetchone()

            cursor.execute("""
                SELECT s.id::text, s.season_num, 
                       COUNT(e.id) as episodes_count
                FROM cinema.seasons s
                LEFT JOIN cinema.episodes e ON e.season_id = s.id
                WHERE s.content_id = %s
                GROUP BY s.id, s.season_num
                ORDER BY s.season_num
            """, [series_id])
            seasons = cursor.fetchall()
    
    return render(request, 'employees/admin/content/admin_seasons.html', {
        'series_list': series_list,
        'selected_series': selected_series,
        'seasons': seasons,
        'series_id': series_id,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_season_add(request, series_id):
    """Добавление нового сезона"""
    from django.db import connection
    from django.contrib import messages
    
    if request.method == 'POST':
        try:
            season_num = int(request.POST.get('season_num', 0))
            description = request.POST.get('description', '')
            
            if season_num <= 0:
                messages.error(request, 'Номер сезона должен быть положительным числом')
                return redirect('admin_season_add', series_id=series_id)
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 1 FROM cinema.seasons 
                    WHERE content_id = %s AND season_num = %s
                """, [series_id, season_num])
                
                if cursor.fetchone():
                    messages.error(request, f'Сезон {season_num} уже существует')
                    return redirect('admin_season_add', series_id=series_id)
                

                cursor.execute("""
                    INSERT INTO cinema.seasons 
                    (id, content_id, season_num)
                    VALUES (gen_random_uuid(), %s, %s)
                    RETURNING id::text
                """, [series_id, season_num])
                
                season_id = cursor.fetchone()[0]
                messages.success(request, f'Сезон {season_num} успешно добавлен!')
                return redirect('admin_season_detail', season_id=season_id)
                
        except Exception as e:
            messages.error(request, f'Ошибка при добавлении сезона: {str(e)}')
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT title FROM cinema.content 
            WHERE id = %s AND type = 'series'
        """, [series_id])
        series = cursor.fetchone()
        
        if not series:
            messages.error(request, 'Сериал не найден')
            return redirect('admin_seasons_management')
        
        cursor.execute("""
            SELECT COALESCE(MAX(season_num), 0) + 1 as next_season_num
            FROM cinema.seasons 
            WHERE content_id = %s
        """, [series_id])
        next_season = cursor.fetchone()[0]
    
    return render(request, 'employees/admin/content/add/admin_season_add.html', {
        'series_title': series[0],
        'series_id': series_id,
        'next_season': next_season,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_episode_add(request, season_id):
    """Добавление нового эпизода"""
    from django.db import connection
    from django.contrib import messages
    import decimal
    from decimal import Decimal
    
    if request.method == 'POST':
        try:
            episode_num = int(request.POST.get('episode_num', 0))
            title = request.POST.get('title', '').strip()
            description = request.POST.get('description', '').strip()
            duration_str = request.POST.get('duration', '0')
            video_url = sanitize_url(request.POST.get('video_url', ''))
            
            if episode_num <= 0:
                messages.error(request, 'Номер эпизода должен быть положительным числом')
                return redirect('admin_episode_add', season_id=season_id)
            
            if not title:
                messages.error(request, 'Название эпизода обязательно')
                return redirect('admin_episode_add', season_id=season_id)
            

            try:
                duration_sec = int(duration_str)
            except (ValueError, TypeError):
                duration_sec = 0
            
            with connection.cursor() as cursor:

                cursor.execute("""
                    SELECT 1 FROM cinema.episodes 
                    WHERE season_id = %s AND episode_num = %s
                """, [season_id, episode_num])
                
                if cursor.fetchone():
                    messages.error(request, f'Эпизод {episode_num} уже существует в этом сезоне')
                    return redirect('admin_episode_add', season_id=season_id)
                

                video_id = None
                if is_valid_url(video_url):
                    video_id = update_or_create_media(cursor, None, video_url, 'video')

                cursor.execute("""
                    INSERT INTO cinema.episodes 
                    (id, season_id, episode_num, title, description, 
                     duration_sec, video_id)
                    VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s)
                    RETURNING id::text
                """, [season_id, episode_num, title, description, duration_sec, video_id])
                
                episode_id = cursor.fetchone()[0]
                messages.success(request, f'Эпизод "{title}" успешно добавлен!')
                return redirect('admin_season_detail', season_id=season_id)
                
        except Exception as e:
            messages.error(request, f'Ошибка при добавлении эпизода: {str(e)}')
    

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT s.season_num, c.title as series_title
            FROM cinema.seasons s
            JOIN cinema.content c ON c.id = s.content_id
            WHERE s.id = %s
        """, [season_id])
        
        season_info = cursor.fetchone()
        if not season_info:
            messages.error(request, 'Сезон не найден')
            return redirect('admin_seasons_management')
        
        season_num, series_title = season_info
        

        cursor.execute("""
            SELECT COALESCE(MAX(episode_num), 0) + 1 as next_episode_num
            FROM cinema.episodes 
            WHERE season_id = %s
        """, [season_id])
        next_episode = cursor.fetchone()[0]
    
    return render(request, 'employees/admin/content/add/admin_episode_add.html', {
        'season_id': season_id,
        'season_num': season_num,
        'series_title': series_title,
        'next_episode': next_episode,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_episode_edit(request, episode_id):
    """Редактирование эпизода"""
    from django.db import connection
    from django.contrib import messages
    import decimal
    from decimal import Decimal
    
    if request.method == 'POST':
        try:
            episode_num = int(request.POST.get('episode_num', 0))
            title = request.POST.get('title', '').strip()
            description = request.POST.get('description', '').strip()
            duration_str = request.POST.get('duration', '0')
            video_url = sanitize_url(request.POST.get('video_url', ''))
            
            if episode_num <= 0:
                messages.error(request, 'Номер эпизода должен быть положительным числом')
                return redirect('admin_episode_edit', episode_id=episode_id)
            
            if not title:
                messages.error(request, 'Название эпизода обязательно')
                return redirect('admin_episode_edit', episode_id=episode_id)
            

            try:
                duration_sec = int(duration_str)
            except (ValueError, TypeError):
                duration_sec = 0
            
            with connection.cursor() as cursor:

                cursor.execute("""
                    SELECT season_id FROM cinema.episodes WHERE id = %s
                """, [episode_id])
                result = cursor.fetchone()
                if not result:
                    messages.error(request, 'Эпизод не найден')
                    return redirect('admin_seasons_management')
                
                season_id = result[0]

                cursor.execute("""
                    SELECT 1 FROM cinema.episodes 
                    WHERE season_id = %s AND episode_num = %s AND id != %s
                """, [season_id, episode_num, episode_id])
                
                if cursor.fetchone():
                    messages.error(request, f'Эпизод {episode_num} уже существует в этом сезоне')
                    return redirect('admin_episode_edit', episode_id=episode_id)
                

                cursor.execute("""
                    SELECT video_id FROM cinema.episodes WHERE id = %s
                """, [episode_id])
                current_video_id = cursor.fetchone()[0]
                

                video_id = None
                if is_valid_url(video_url):
                    video_id = update_or_create_media(cursor, current_video_id, video_url, 'video')

                cursor.execute("""
                    UPDATE cinema.episodes 
                    SET episode_num = %s, title = %s, description = %s,
                        duration_sec = %s, video_id = %s
                    WHERE id = %s
                """, [episode_num, title, description, duration_sec, video_id, episode_id])
                
                messages.success(request, f'Эпизод "{title}" успешно обновлен!')
                return redirect('admin_season_detail', season_id=season_id)
                
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении эпизода: {str(e)}')
    

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                e.episode_num, e.title, e.description, 
                e.duration_sec, ma.url as video_url,
                s.season_num, c.title as series_title,
                s.id::text as season_id
            FROM cinema.episodes e
            JOIN cinema.seasons s ON s.id = e.season_id
            JOIN cinema.content c ON c.id = s.content_id
            LEFT JOIN cinema.media_assets ma ON ma.id = e.video_id
            WHERE e.id = %s
        """, [episode_id])
        
        episode_info = cursor.fetchone()
        if not episode_info:
            messages.error(request, 'Эпизод не найден')
            return redirect('admin_seasons_management')
        
        (episode_num, title, description, duration_sec, video_url, 
         season_num, series_title, season_id) = episode_info
    
    return render(request, 'employees/admin/content/edit/admin_episode_edit.html', {
        'episode_id': episode_id,
        'episode_num': episode_num,
        'title': title,
        'description': description,
        'duration_sec': duration_sec,
        'video_url': video_url or '',
        'season_id': season_id,
        'season_num': season_num,
        'series_title': series_title,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_season_delete(request, season_id):
    """Удаление сезона"""
    from django.db import connection
    from django.contrib import messages
    
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:

                cursor.execute("""
                    SELECT s.season_num, c.title 
                    FROM cinema.seasons s
                    JOIN cinema.content c ON c.id = s.content_id
                    WHERE s.id = %s
                """, [season_id])
                
                result = cursor.fetchone()
                if result:
                    season_num, series_title = result
                    

                    cursor.execute("DELETE FROM cinema.seasons WHERE id = %s", [season_id])
                    
                    messages.success(request, f'Сезон {season_num} сериала "{series_title}" успешно удален!')
                else:
                    messages.error(request, 'Сезон не найден')
        except Exception as e:
            messages.error(request, f'Ошибка при удалении сезона: {str(e)}')
    
    return redirect('admin_seasons_management')

@employee_required
@check_employee_role('ADMIN')
def admin_episode_delete(request, episode_id):
    """Удаление эпизода"""
    from django.db import connection
    from django.contrib import messages
    
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:

                cursor.execute("""
                    SELECT e.title, s.season_num, c.title as series_title
                    FROM cinema.episodes e
                    JOIN cinema.seasons s ON s.id = e.season_id
                    JOIN cinema.content c ON c.id = s.content_id
                    WHERE e.id = %s
                """, [episode_id])
                
                result = cursor.fetchone()
                if result:
                    episode_title, season_num, series_title = result
                    

                    cursor.execute("DELETE FROM cinema.episodes WHERE id = %s", [episode_id])
                    
                    messages.success(request, f'Эпизод "{episode_title}" (сезон {season_num}) успешно удален!')
                else:
                    messages.error(request, 'Эпизод не найден')
        except Exception as e:
            messages.error(request, f'Ошибка при удалении эпизода: {str(e)}')
    
    return redirect(request.POST.get('next', 'admin_seasons_management'))

@employee_required
@check_employee_role('ADMIN')
def admin_season_detail(request, season_id):
    """Детали сезона с эпизодами"""
    from django.db import connection
    from django.contrib import messages
    
    with connection.cursor() as cursor:

        cursor.execute("""
            SELECT s.id::text, s.season_num, c.id::text, c.title as series_title
            FROM cinema.seasons s
            JOIN cinema.content c ON c.id = s.content_id
            WHERE s.id = %s
        """, [season_id])
        
        season_info = cursor.fetchone()
        if not season_info:
            messages.error(request, 'Сезон не найден')
            return redirect('admin_seasons_management')
        
        season_id, season_num, series_id, series_title = season_info
        

        cursor.execute("""
            SELECT 
                e.id::text, 
                e.episode_num, 
                e.title, 
                e.description,
                e.duration_sec,
                ma.url as video_url
            FROM cinema.episodes e
            LEFT JOIN cinema.media_assets ma ON ma.id = e.video_id
            WHERE e.season_id = %s
            ORDER BY e.episode_num
        """, [season_id])
        episodes = cursor.fetchall()
    
    return render(request, 'employees/admin/content/admin_season_detail.html', {
        'season_id': season_id,
        'season_num': season_num,
        'series_id': series_id,
        'series_title': series_title,
        'episodes': episodes,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_media_assets(request):
    """Управление медиафайлами"""
    from django.db import connection
    from django.contrib import messages
    
    search_query = request.GET.get('search', '').strip()
    kind_filter = request.GET.get('kind', 'all')
    

    if request.method == 'POST':
        action = request.POST.get('action')
        asset_id = request.POST.get('asset_id')
        
        if action == 'create':
            try:
                url = request.POST.get('url', '').strip()
                kind = request.POST.get('kind', 'image')
                mime_type = request.POST.get('mime_type', '')
                
                if not url:
                    messages.error(request, 'URL обязателен')
                elif not url.startswith(('http://', 'https://')):
                    messages.error(request, 'URL должен начинаться с http:// или https://')
                else:
                    with connection.cursor() as cursor:

                        if not mime_type:
                            mime_type = get_mime_type_by_url(url, kind)

                        cursor.execute("""
                            INSERT INTO cinema.media_assets 
                            (id, kind, mime_type, url, created_at)
                            VALUES (gen_random_uuid(), %s, %s, %s, NOW())
                        """, [kind, mime_type, url])
                        
                        messages.success(request, 'Медиа-актив успешно создан')
                        
            except Exception as e:
                messages.error(request, f'Ошибка при создании медиа-актива: {str(e)}')
                
        elif action == 'edit':
            try:
                url = request.POST.get('url', '').strip()
                kind = request.POST.get('kind', 'image')
                mime_type = request.POST.get('mime_type', '')
                
                if not asset_id:
                    messages.error(request, 'ID медиа-актива обязателен')
                elif not url:
                    messages.error(request, 'URL обязателен')
                elif not url.startswith(('http://', 'https://')):
                    messages.error(request, 'URL должен начинаться с http:// или https://')
                else:
                    with connection.cursor() as cursor:

                        if not mime_type:
                            mime_type = get_mime_type_by_url(url, kind)

                        cursor.execute("""
                            UPDATE cinema.media_assets 
                            SET url = %s, kind = %s, mime_type = %s
                            WHERE id = %s
                        """, [url, kind, mime_type, asset_id])
                        
                        messages.success(request, 'Медиа-актив успешно обновлен')
                        
            except Exception as e:
                messages.error(request, f'Ошибка при обновлении медиа-актива: {str(e)}')
                
        elif action == 'delete':
            try:
                with connection.cursor() as cursor:

                    cursor.execute("""
                        SELECT 
                            (SELECT COUNT(*) FROM cinema.content WHERE video_id = %s) as video_count,
                            (SELECT COUNT(*) FROM cinema.content WHERE cover_image_id = %s) as cover_count,
                            (SELECT COUNT(*) FROM cinema.content WHERE trailer_id = %s) as trailer_count,
                            (SELECT COUNT(*) FROM cinema.content WHERE cover_image_wide_id = %s) as wide_count,
                            (SELECT COUNT(*) FROM cinema.episodes WHERE video_id = %s) as episode_count
                    """, [asset_id, asset_id, asset_id, asset_id, asset_id])
                    
                    result = cursor.fetchone()
                    video_count, cover_count, trailer_count, wide_count, episode_count = result
                    
                    total_usage = (video_count or 0) + (cover_count or 0) + (trailer_count or 0) + (wide_count or 0) + (episode_count or 0)
                    
                    if total_usage > 0:

                        cursor.execute("""
                            -- Очищаем ссылки в таблице content
                            UPDATE cinema.content SET video_id = NULL WHERE video_id = %s;
                            UPDATE cinema.content SET cover_image_id = NULL WHERE cover_image_id = %s;
                            UPDATE cinema.content SET trailer_id = NULL WHERE trailer_id = %s;
                            UPDATE cinema.content SET cover_image_wide_id = NULL WHERE cover_image_wide_id = %s;
                            
                            -- Очищаем ссылки в таблице episodes
                            UPDATE cinema.episodes SET video_id = NULL WHERE video_id = %s;
                        """, [asset_id, asset_id, asset_id, asset_id, asset_id])
                        
                        cursor.execute("DELETE FROM cinema.media_assets WHERE id = %s", [asset_id])
                        
                        messages.warning(request, 
                            f'Медиафайл удален. {total_usage} ссылок на него были очищены.')
                    else:

                        cursor.execute("DELETE FROM cinema.media_assets WHERE id = %s", [asset_id])
                        messages.success(request, 'Неиспользуемый медиафайл удален')
                        
            except Exception as e:
                messages.error(request, f'Ошибка при удалении медиафайла: {str(e)}')
                logger.error(f"Error deleting media asset {asset_id}: {e}")

    query = """
        SELECT 
            ma.id::text, ma.kind, ma.mime_type, ma.url, 
            ma.size_bytes, ma.created_at,
            COALESCE((SELECT COUNT(*) FROM cinema.content WHERE video_id = ma.id), 0) as video_usage,
            COALESCE((SELECT COUNT(*) FROM cinema.content WHERE cover_image_id = ma.id), 0) as cover_usage,
            COALESCE((SELECT COUNT(*) FROM cinema.content WHERE trailer_id = ma.id), 0) as trailer_usage,
            COALESCE((SELECT COUNT(*) FROM cinema.content WHERE cover_image_wide_id = ma.id), 0) as wide_usage,
            COALESCE((SELECT COUNT(*) FROM cinema.episodes WHERE video_id = ma.id), 0) as episode_usage
        FROM cinema.media_assets ma
    """
    
    where_clauses = []
    params = []
    
    if search_query:
        where_clauses.append("(ma.url ILIKE %s OR ma.mime_type ILIKE %s)")
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    
    if kind_filter and kind_filter != 'all':
        where_clauses.append("ma.kind = %s")
        params.append(kind_filter)
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    query += " ORDER BY ma.created_at DESC LIMIT 100"
    
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        media_assets = cursor.fetchall()
        

        cursor.execute("""
            SELECT kind, COUNT(*) as count
            FROM cinema.media_assets
            GROUP BY kind
            ORDER BY count DESC
        """)
        kind_stats = cursor.fetchall()
        

        used_count = 0
        for media in media_assets:

            total_usage = (media[6] or 0) + (media[7] or 0) + (media[8] or 0) + (media[9] or 0) + (media[10] or 0)
            if total_usage > 0:
                used_count += 1
    
    return render(request, 'employees/admin/content/admin_media_assets.html', {
        'media_assets': media_assets,
        'kind_stats': kind_stats,
        'employee_name': request.session.get('employee_name'),
        'search_query': search_query,
        'current_kind': kind_filter,
        'total_count': len(media_assets),
        'used_count': used_count,
    })


def get_mime_type_by_url(url, kind):
    """Определяет MIME-тип по URL и типу"""
    if kind == 'video':
        if url.endswith('.mp4'):
            return 'video/mp4'
        elif url.endswith('.webm'):
            return 'video/webm'
        elif url.endswith('.m3u8'):
            return 'application/vnd.apple.mpegurl'
        elif url.endswith('.mpd'):
            return 'application/dash+xml'
        elif url.endswith('.avi'):
            return 'video/x-msvideo'
        elif url.endswith('.mov'):
            return 'video/quicktime'
        else:
            return 'video/mp4'
    elif kind == 'image':
        if url.endswith('.jpg') or url.endswith('.jpeg'):
            return 'image/jpeg'
        elif url.endswith('.png'):
            return 'image/png'
        elif url.endswith('.gif'):
            return 'image/gif'
        elif url.endswith('.webp'):
            return 'image/webp'
        elif url.endswith('.svg'):
            return 'image/svg+xml'
        elif url.endswith('.bmp'):
            return 'image/bmp'
        else:
            return 'image/jpeg'
    elif kind == 'audio':
        if url.endswith('.mp3'):
            return 'audio/mpeg'
        elif url.endswith('.wav'):
            return 'audio/wav'
        elif url.endswith('.ogg'):
            return 'audio/ogg'
        elif url.endswith('.m4a'):
            return 'audio/mp4'
        else:
            return 'audio/mpeg'
    else:
        return 'application/octet-stream'


@employee_required
@check_employee_role('ADMIN')
@employee_required
@check_employee_role('ADMIN')
def admin_panel(request):
    """Панель администратора"""
    from django.db import connection
    
    with connection.cursor() as cursor:

        cursor.execute("SELECT COUNT(*) FROM cinema.users")
        total_users = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM cinema.user_subscriptions 
            WHERE status = 'active' AND expires_at > NOW()
        """)
        active_subscriptions = cursor.fetchone()[0]
        

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM cinema.payments 
            WHERE status = 'paid'
        """)
        total_revenue = cursor.fetchone()[0]
        

        cursor.execute("SELECT COUNT(*) FROM cinema.content")
        total_content = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cinema.content WHERE type = 'movie'")
        total_movies = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cinema.content WHERE type = 'series'")
        total_series = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cinema.content WHERE is_free = true")
        total_free_content = cursor.fetchone()[0]
        

        cursor.execute("""
            SELECT 
                c.id::text, 
                c.title, 
                c.type, 
                c.release_year, 
                c.is_free, 
                c.price, 
                c.created_at
            FROM cinema.content c
            ORDER BY c.created_at DESC 
            LIMIT 5
        """)

        recent_content_data = []
        columns = ['id', 'title', 'type', 'release_year', 'is_free', 'price', 'created_at']
        rows = cursor.fetchall()
        
        for row in rows:
            content_dict = {}
            for i, col_name in enumerate(columns):
                content_dict[col_name] = row[i]
            recent_content_data.append(content_dict)
    
    return render(request, 'employees/admin/admin_panel.html', {
        'employee_name': request.session.get('employee_name'),
        'employee_email': request.session.get('employee_email'),
        'employee_roles': request.session.get('employee_roles', []),
        'total_users': total_users,
        'active_subscriptions': active_subscriptions,
        'total_revenue': total_revenue,
        'total_content': total_content,
        'total_movies': total_movies,
        'total_series': total_series,
        'total_free_content': total_free_content,
        'recent_content': recent_content_data,
    })

@employee_required
@check_employee_role('ANALYST')
def analytics_panel(request):
    """Расширенная панель аналитика/финансиста"""
    from django.db import connection
    import datetime
    from decimal import Decimal
    import json
    

    period = request.GET.get('period', '7d')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    now = datetime.datetime.now()
    end_date = now
    
    if period == 'all':
        start_date = datetime.datetime(2020, 1, 1)
        end_date = now
    elif start_date_str and end_date_str:
        try:
            start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d') + datetime.timedelta(days=1)
        except:

            start_date = end_date - datetime.timedelta(days=7)
    else:
        if period == '30d':
            start_date = end_date - datetime.timedelta(days=30)
        elif period == '90d':
            start_date = end_date - datetime.timedelta(days=90)
        else:
            start_date = end_date - datetime.timedelta(days=7)
    

    start_date_display = start_date.date()
    end_date_display = (end_date - datetime.timedelta(days=1)).date()


    start_date_sql = start_date.strftime('%Y-%m-%d %H:%M:%S')
    end_date_sql = end_date.strftime('%Y-%m-%d %H:%M:%S')
    

    registrations = []
    purchases = []
    daily_revenue = []
    subscription_payments = []
    financial_stats = None
    subscription_stats = []
    popular_content = []
    user_activity = None
    payment_methods = []
    genre_stats = []
    conversion_stats = None
    arpu_stats = None
    retention_stats = []
    geography_stats = []
    subscription_types_formatted = []
    total_subscriptions_sold = 0
    total_subscriptions_revenue_all = 0
    total_paid_subscriptions = 0
    total_active_subscriptions = 0
    
    with connection.cursor() as cursor:

        cursor.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM cinema.users
            WHERE created_at BETWEEN %s AND %s
            GROUP BY DATE(created_at)
            ORDER BY date
        """, [start_date_sql, end_date_sql])
        registrations = cursor.fetchall()
        

        cursor.execute("""
            SELECT DATE(purchased_at) as date, COUNT(*) as count, 
                   COALESCE(SUM(c.price), 0) as total_amount
            FROM cinema.purchases p
            JOIN cinema.content c ON c.id = p.content_id
            WHERE p.purchased_at BETWEEN %s AND %s
            GROUP BY DATE(purchased_at)
            ORDER BY date
        """, [start_date_sql, end_date_sql])
        purchases = cursor.fetchall()
        
        cursor.execute("""
            SELECT DATE(paid_at) as date, COUNT(*) as count, 
                   COALESCE(SUM(amount), 0) as total_amount
            FROM cinema.payments
            WHERE paid_at BETWEEN %s AND %s
              AND subscription_id IS NOT NULL
            GROUP BY DATE(paid_at)
            ORDER BY date
        """, [start_date_sql, end_date_sql])
        subscription_payments = cursor.fetchall()
        

        cursor.execute("""
            WITH all_revenue AS (
                -- Выручка от подписок (оплаченные платежи)
                SELECT 
                    'subscription' as revenue_type,
                    COUNT(*) as total_payments,
                    COALESCE(SUM(amount), 0) as total_revenue,
                    COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) as paid_amount,
                    COALESCE(SUM(CASE WHEN status = 'failed' THEN amount ELSE 0 END), 0) as failed_amount,
                    COALESCE(SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END), 0) as pending_amount,
                    COUNT(CASE WHEN status = 'paid' THEN 1 END) as paid_count,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_count,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_count
                FROM cinema.payments
                WHERE paid_at BETWEEN %s AND %s
                AND subscription_id IS NOT NULL
                
                UNION ALL
                
                -- Выручка от покупок контента
                SELECT 
                    'purchase' as revenue_type,
                    COUNT(pur.id) as total_payments,
                    COALESCE(SUM(c.price), 0) as total_revenue,
                    COALESCE(SUM(CASE WHEN p.status = 'paid' THEN p.amount ELSE 0 END), 0) as paid_amount,
                    COALESCE(SUM(CASE WHEN p.status = 'failed' THEN p.amount ELSE 0 END), 0) as failed_amount,
                    COALESCE(SUM(CASE WHEN p.status = 'pending' THEN p.amount ELSE 0 END), 0) as pending_amount,
                    COUNT(CASE WHEN p.status = 'paid' THEN 1 END) as paid_count,
                    COUNT(CASE WHEN p.status = 'failed' THEN 1 END) as failed_count,
                    COUNT(CASE WHEN p.status = 'pending' THEN 1 END) as pending_count
                FROM cinema.purchases pur
                JOIN cinema.content c ON c.id = pur.content_id
                LEFT JOIN cinema.payments p ON p.purchase_id = pur.id
                WHERE pur.purchased_at BETWEEN %s AND %s
                AND NOT c.is_free AND c.price > 0
            )
            SELECT 
                SUM(total_payments) as total_payments,
                SUM(total_revenue) as total_revenue,
                SUM(paid_amount) as paid_amount,
                SUM(failed_amount) as failed_amount,
                SUM(pending_amount) as pending_amount,
                SUM(paid_count) as paid_count,
                SUM(failed_count) as failed_count,
                SUM(pending_count) as pending_count,
                CASE 
                    WHEN SUM(paid_count) > 0 
                    THEN SUM(paid_amount) / SUM(paid_count)
                    ELSE 0 
                END as avg_paid_amount,
                CASE 
                    WHEN SUM(failed_count) > 0 
                    THEN SUM(failed_amount) / SUM(failed_count)
                    ELSE 0 
                END as avg_failed_amount
            FROM all_revenue
        """, [start_date_sql, end_date_sql, start_date_sql, end_date_sql])
        financial_stats = cursor.fetchone()

        cursor.execute("""
            SELECT 
                c.title as content_title,
                c.type as content_type,
                COUNT(p.id) as purchase_count,
                COALESCE(SUM(c.price), 0) as total_revenue,
                COALESCE(AVG(cr.rating), 0) as avg_rating
            FROM cinema.purchases p
            JOIN cinema.content c ON c.id = p.content_id
            LEFT JOIN cinema.content_reviews cr ON cr.content_id = c.id
            WHERE p.purchased_at BETWEEN %s AND %s
            GROUP BY c.id, c.title, c.type
            ORDER BY purchase_count DESC
            LIMIT 10
        """, [start_date_sql, end_date_sql])
        popular_content = cursor.fetchall()

        cursor.execute("""
            SELECT 
                COUNT(DISTINCT user_id) as active_users,
                COUNT(*) as total_sessions,
                COALESCE(AVG(session_duration), 0) as avg_session_duration
            FROM (
                SELECT 
                    user_id,
                    session_start,
                    EXTRACT(EPOCH FROM (session_end - session_start)) as session_duration
                FROM (
                    SELECT 
                        user_id,
                        MIN(watched_at) as session_start,
                        MAX(watched_at) as session_end
                    FROM cinema.watch_history
                    WHERE watched_at BETWEEN %s AND %s
                    GROUP BY user_id, DATE(watched_at)
                ) sessions
            ) user_sessions
        """, [start_date, end_date])
        user_activity = cursor.fetchone()

        cursor.execute("""
            SELECT DATE(paid_at) as date, 
                   COALESCE(SUM(amount), 0) as daily_revenue
            FROM cinema.payments
            WHERE paid_at BETWEEN %s AND %s
              AND status = 'paid'
            GROUP BY DATE(paid_at)
            ORDER BY date
        """, [start_date_sql, end_date_sql])
        daily_revenue = cursor.fetchall()

        try:
            cursor.execute("""
                SELECT 
                    payment_method,
                    COUNT(*) as count,
                    COALESCE(SUM(amount), 0) as total_amount
                FROM cinema.payments
                WHERE paid_at BETWEEN %s AND %s
                  AND payment_method IS NOT NULL
                GROUP BY payment_method
                ORDER BY total_amount DESC
            """, [start_date, end_date])
            payment_methods = cursor.fetchall()
        except:
            payment_methods = []
        
        cursor.execute("""
            SELECT 
                g.name as genre_name,
                COUNT(DISTINCT p.content_id) as content_count,
                COUNT(p.id) as purchase_count,
                COALESCE(SUM(c.price), 0) as total_revenue
            FROM cinema.purchases p
            JOIN cinema.content c ON c.id = p.content_id
            JOIN cinema.content_genres cg ON cg.content_id = c.id
            JOIN cinema.genres g ON g.id = cg.genre_id
            WHERE p.purchased_at BETWEEN %s AND %s
            GROUP BY g.id, g.name
            ORDER BY total_revenue DESC
            LIMIT 15
        """, [start_date, end_date])
        genre_stats = cursor.fetchall()
        
        cursor.execute("""
            WITH user_registrations AS (
                SELECT u.id, u.created_at,
                       EXISTS(SELECT 1 FROM cinema.purchases p WHERE p.user_id = u.id) as has_purchase,
                       EXISTS(SELECT 1 FROM cinema.user_subscriptions us WHERE us.user_id = u.id) as has_subscription
                FROM cinema.users u
                WHERE u.created_at BETWEEN %s AND %s
            )
            SELECT 
                COUNT(*) as total_registered,
                SUM(CASE WHEN has_purchase THEN 1 ELSE 0 END) as bought_content,
                SUM(CASE WHEN has_subscription THEN 1 ELSE 0 END) as has_subscription,
                ROUND(100.0 * SUM(CASE WHEN has_purchase OR has_subscription THEN 1 ELSE 0 END) / COUNT(*), 2) as conversion_rate
            FROM user_registrations
        """, [start_date, end_date])
        conversion_stats = cursor.fetchone()
        
        cursor.execute("""
            WITH user_revenue AS (
                SELECT 
                    p.user_id,
                    COALESCE(SUM(p2.amount), 0) as total_spent
                FROM cinema.purchases p
                LEFT JOIN cinema.payments p2 ON p2.purchase_id = p.id
                WHERE p.purchased_at BETWEEN %s AND %s
                GROUP BY p.user_id
                UNION ALL
                SELECT 
                    us.user_id,
                    COALESCE(SUM(p.amount), 0) as total_spent
                FROM cinema.user_subscriptions us
                LEFT JOIN cinema.payments p ON p.subscription_id = us.id
                WHERE us.started_at BETWEEN %s AND %s
                GROUP BY us.user_id
            )
            SELECT 
                COUNT(DISTINCT user_id) as paying_users,
                COALESCE(SUM(total_spent), 0) as total_revenue_users,
                CASE 
                    WHEN COUNT(DISTINCT user_id) > 0 
                    THEN COALESCE(SUM(total_spent), 0) / COUNT(DISTINCT user_id)
                    ELSE 0 
                END as arpu
            FROM user_revenue
            WHERE total_spent > 0
        """, [start_date, end_date, start_date, end_date])
        arpu_stats = cursor.fetchone()

        cursor.execute("""
            WITH cohort_users AS (
                SELECT u.id, DATE_TRUNC('week', u.created_at) as cohort_week
                FROM cinema.users u
                WHERE u.created_at BETWEEN %s AND %s
            ),
            weekly_activity AS (
                SELECT 
                    cu.cohort_week,
                    DATE_TRUNC('week', wh.watched_at) as activity_week,
                    COUNT(DISTINCT wh.user_id) as active_users
                FROM cohort_users cu
                JOIN cinema.watch_history wh ON wh.user_id = cu.id
                WHERE wh.watched_at BETWEEN %s AND %s
                GROUP BY cu.cohort_week, DATE_TRUNC('week', wh.watched_at)
            )
            SELECT 
                TO_CHAR(cohort_week, 'YYYY-MM-DD') as cohort,
                COUNT(DISTINCT cu.id) as cohort_size,
                ROUND(100.0 * COUNT(DISTINCT CASE 
                    WHEN DATE_TRUNC('week', wh.watched_at) = cohort_week THEN wh.user_id 
                END) / COUNT(DISTINCT cu.id), 2) as week_0,
                ROUND(100.0 * COUNT(DISTINCT CASE 
                    WHEN DATE_TRUNC('week', wh.watched_at) = cohort_week + INTERVAL '1 week' THEN wh.user_id 
                END) / COUNT(DISTINCT cu.id), 2) as week_1,
                ROUND(100.0 * COUNT(DISTINCT CASE 
                    WHEN DATE_TRUNC('week', wh.watched_at) = cohort_week + INTERVAL '2 weeks' THEN wh.user_id 
                END) / COUNT(DISTINCT cu.id), 2) as week_2,
                ROUND(100.0 * COUNT(DISTINCT CASE 
                    WHEN DATE_TRUNC('week', wh.watched_at) = cohort_week + INTERVAL '3 weeks' THEN wh.user_id 
                END) / COUNT(DISTINCT cu.id), 2) as week_3
            FROM cohort_users cu
            LEFT JOIN cinema.watch_history wh ON wh.user_id = cu.id
            GROUP BY cohort_week
            ORDER BY cohort_week DESC
            LIMIT 8
        """, [start_date - datetime.timedelta(days=30), end_date, start_date - datetime.timedelta(days=30), end_date])
        retention_stats = cursor.fetchall()
        
        try:
            cursor.execute("""
                SELECT 
                    country,
                    city,
                    COUNT(*) as user_count,
                    COALESCE(SUM(
                        CASE WHEN EXISTS(
                            SELECT 1 FROM cinema.purchases p WHERE p.user_id = u.id
                        ) THEN 1 ELSE 0 END
                    ), 0) as paying_users
                FROM cinema.users u
                WHERE u.created_at BETWEEN %s AND %s
                  AND country IS NOT NULL
                GROUP BY country, city
                ORDER BY user_count DESC
                LIMIT 20
            """, [start_date, end_date])
            geography_stats = cursor.fetchall()
        except:
            geography_stats = []

        try:
            cursor.execute("""
                SELECT COUNT(*) FROM cinema.payments 
                WHERE status IN ('failed', 'pending')
                AND paid_at BETWEEN %s AND %s
            """, [start_date, end_date])
            has_payment_issues = cursor.fetchone()[0] > 0
        except Exception as e:
            print(f"DEBUG: Error checking payment issues: {e}")
            has_payment_issues = False

        cursor.execute("""
            WITH subscription_payments_period AS (
                -- Платежи за выбранный период
                SELECT 
                    us.plan_id,
                    COUNT(DISTINCT p.id) as payment_count,
                    COUNT(DISTINCT us.id) as subscription_count,
                    COALESCE(SUM(p.amount), 0) as total_revenue,
                    COUNT(DISTINCT CASE WHEN p.status = 'paid' THEN us.id END) as paid_subscriptions,
                    COALESCE(SUM(CASE WHEN p.status = 'paid' THEN p.amount ELSE 0 END), 0) as paid_revenue
                FROM cinema.payments p
                JOIN cinema.user_subscriptions us ON us.id = p.subscription_id
                WHERE p.paid_at BETWEEN %s AND %s
                AND p.status IN ('paid', 'pending')
                GROUP BY us.plan_id
            ),
            active_subscriptions_count AS (
                -- Активные подписки на текущий момент
                SELECT 
                    plan_id,
                    COUNT(*) as active_count
                FROM cinema.user_subscriptions
                WHERE status = 'active' 
                AND (expires_at IS NULL OR expires_at > NOW())
                AND started_at <= %s
                GROUP BY plan_id
            )
            SELECT 
                sp.id,
                sp.code,
                sp.name,
                sp.period_months,
                sp.price,
                COALESCE(spp.subscription_count, 0) as total_subscriptions,
                COALESCE(spp.paid_subscriptions, 0) as paid_subscriptions,
                COALESCE(spp.paid_revenue, 0) as total_revenue,
                COALESCE(ascount.active_count, 0) as active_subscriptions,
                CASE 
                    WHEN COALESCE(spp.paid_subscriptions, 0) > 0 
                    THEN COALESCE(spp.paid_revenue, 0) / COALESCE(spp.paid_subscriptions, 1)
                    ELSE 0 
                END as avg_revenue_per_sub
            FROM cinema.subscription_plans sp
            LEFT JOIN subscription_payments_period spp ON spp.plan_id = sp.id
            LEFT JOIN active_subscriptions_count ascount ON ascount.plan_id = sp.id
            WHERE sp.code != 'ADMIN_ACCESS'
            ORDER BY COALESCE(spp.total_revenue, 0) DESC
        """, [start_date_sql, end_date_sql, end_date_sql])
        subscription_types_data = cursor.fetchall()

        cursor.execute("""
            SELECT 
                DATE_TRUNC('month', p.paid_at) as month,
                sp.name as plan_name,
                COUNT(DISTINCT p.subscription_id) as sales_count,
                COALESCE(SUM(p.amount), 0) as monthly_revenue
            FROM cinema.payments p
            JOIN cinema.user_subscriptions us ON us.id = p.subscription_id
            JOIN cinema.subscription_plans sp ON sp.id = us.plan_id
            WHERE p.status = 'paid'
            AND sp.code != 'ADMIN_ACCESS'
            AND p.paid_at BETWEEN %s AND %s
            GROUP BY DATE_TRUNC('month', p.paid_at), sp.id, sp.name
            ORDER BY month, monthly_revenue DESC
        """, [start_date_sql, end_date_sql])
        subscription_dynamics = cursor.fetchall()


        subscription_types_formatted = []
        total_subscriptions_sold = 0
        total_subscriptions_revenue_all = 0
        total_paid_subscriptions = 0
    
    for row in subscription_types_data:

        if len(row) == 10:
            plan_id, plan_code, plan_name, period_months, plan_price, total_subs, paid_subs, revenue, active_subs, avg_revenue = row
            
            subscription_types_formatted.append({
                'id': plan_id,
                'code': plan_code,
                'name': plan_name,
                'period': f"{period_months} мес.",
                'price': float(plan_price or 0),
                'total_subscriptions': int(total_subs or 0),
                'paid_subscriptions': int(paid_subs or 0),
                'revenue': float(revenue or 0),
                'active_subscriptions': int(active_subs or 0),
                'avg_revenue': float(avg_revenue or 0)
            })
            
            total_subscriptions_sold += int(total_subs or 0)
            total_subscriptions_revenue_all += float(revenue or 0)
            total_paid_subscriptions += int(paid_subs or 0)
            total_active_subscriptions += int(active_subs or 0)
        elif len(row) == 9:
            plan_id, plan_code, plan_name, period_months, plan_price, total_subs, paid_subs, revenue, avg_revenue = row
            
            subscription_types_formatted.append({
                'id': plan_id,
                'code': plan_code,
                'name': plan_name,
                'period': f"{period_months} мес.",
                'price': float(plan_price or 0),
                'total_subscriptions': int(total_subs or 0),
                'paid_subscriptions': int(paid_subs or 0),
                'revenue': float(revenue or 0),
                'active_subscriptions': 0,
                'avg_revenue': float(avg_revenue or 0)
            })
            
            total_subscriptions_sold += int(total_subs or 0)
            total_subscriptions_revenue_all += float(revenue or 0)
            total_paid_subscriptions += int(paid_subs or 0)

    subscription_monthly_data = {}
    monthly_labels = []
    for row in subscription_dynamics:
        month, plan_name, sales_count, monthly_revenue = row
        month_str = month.strftime('%Y-%m')
        month_display = month.strftime('%b %Y')
        
        if month_display not in monthly_labels:
            monthly_labels.append(month_display)
        
        if month_str not in subscription_monthly_data:
            subscription_monthly_data[month_str] = {
                'month': month_display,
                'data': {},
                'total_revenue': 0
            }
        
        subscription_monthly_data[month_str]['data'][plan_name] = {
            'sales': int(sales_count or 0),
            'revenue': float(monthly_revenue or 0)
        }
        subscription_monthly_data[month_str]['total_revenue'] += float(monthly_revenue or 0)


        total_subscriptions_sold = 0
        total_subscriptions_revenue = 0
        if subscription_stats:
            for sub in subscription_stats:
                total_subscriptions_sold += sub[1]
                total_subscriptions_revenue += float(sub[2] or 0)

    subscription_stats_with_avg = []
    for sub in subscription_stats:
        plan_name = sub[0]
        sold_count = sub[1]
        revenue = float(sub[2] or 0)
        avg_price = revenue / sold_count if sold_count > 0 else 0
        subscription_stats_with_avg.append((plan_name, sold_count, revenue, avg_price))


    chart_data = {
        'registrations': [{'date': str(r[0]), 'count': r[1]} for r in registrations],
        'daily_revenue': [{'date': str(r[0]), 'revenue': float(r[1] or 0)} for r in daily_revenue],
        'purchases': [{'date': str(p[0]), 'count': p[1], 'amount': float(p[2] or 0)} for p in purchases],

        'subscriptions': [
            {
                'plan': sub['name'],
                'sold': sub['total_subscriptions'],
                'paid': sub['paid_subscriptions'],
                'revenue': sub['revenue'],
                'code': sub['code'],
                'period': sub['period'],
                'price': sub['price'],
                'avg_revenue': sub['avg_revenue']
            }
            for sub in subscription_types_formatted
        ],

        'subscription_dynamics': {
            'labels': [],
            'datasets': []
        }
    }

    if subscription_dynamics:

        subscription_monthly_data = {}
        monthly_labels = []
        for row in subscription_dynamics:
            month, plan_name, sales_count, monthly_revenue = row
            if month:
                month_str = month.strftime('%Y-%m')
                month_display = month.strftime('%b %Y')
                
                if month_display not in monthly_labels:
                    monthly_labels.append(month_display)
                
                if month_str not in subscription_monthly_data:
                    subscription_monthly_data[month_str] = {
                        'month': month_display,
                        'data': {},
                        'total_revenue': 0
                    }
                
                subscription_monthly_data[month_str]['data'][plan_name] = {
                    'sales': int(sales_count or 0),
                    'revenue': float(monthly_revenue or 0)
                }
                subscription_monthly_data[month_str]['total_revenue'] += float(monthly_revenue or 0)
        

        plan_names = set()
        for month_data in subscription_monthly_data.values():
            for plan_name in month_data['data'].keys():
                plan_names.add(plan_name)
        
        plan_names = list(plan_names)
        colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40']
        

        chart_data['subscription_dynamics']['labels'] = monthly_labels
        
        for i, plan_name in enumerate(plan_names):
            revenue_data = []
            for month_display in monthly_labels:

                month_found = False
                for month_key, month_data in subscription_monthly_data.items():
                    if month_data['month'] == month_display:
                        revenue = month_data['data'].get(plan_name, {}).get('revenue', 0)
                        revenue_data.append(revenue)
                        month_found = True
                        break
                if not month_found:
                    revenue_data.append(0)
            
            chart_data['subscription_dynamics']['datasets'].append({
                'label': plan_name,
                'data': revenue_data,
                'borderColor': colors[i % len(colors)],
                'backgroundColor': colors[i % len(colors)] + '20',
                'tension': 0.4,
                'fill': False
            })
        

        if monthly_labels:
            total_revenue_data = []
            for month_display in monthly_labels:
                total = 0
                for month_key, month_data in subscription_monthly_data.items():
                    if month_data['month'] == month_display:
                        total = month_data['total_revenue']
                        break
                total_revenue_data.append(total)
            
            chart_data['subscription_dynamics']['datasets'].append({
                'label': 'Общая выручка',
                'data': total_revenue_data,
                'borderColor': '#2E7D32',
                'backgroundColor': '#4CAF50',
                'borderWidth': 3,
                'tension': 0.4,
                'fill': False,
                'type': 'line'
            })


    plan_names = set()
    for month_data in subscription_monthly_data.values():
        for plan_name in month_data['data'].keys():
            plan_names.add(plan_name)

    plan_names = list(plan_names)
    colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40']

    for i, plan_name in enumerate(plan_names):
        revenue_data = []
        for month_display in monthly_labels:

            month_found = False
            for month_key, month_data in subscription_monthly_data.items():
                if month_data['month'] == month_display:
                    revenue = month_data['data'].get(plan_name, {}).get('revenue', 0)
                    revenue_data.append(revenue)
                    month_found = True
                    break
            if not month_found:
                revenue_data.append(0)
        
        chart_data['subscription_dynamics']['datasets'].append({
            'label': plan_name,
            'data': revenue_data,
            'borderColor': colors[i % len(colors)],
            'backgroundColor': colors[i % len(colors)] + '20',
            'tension': 0.4,
            'fill': False
        })
    

    total_revenue_data = []
    for month_display in monthly_labels:
        total = 0
        for month_key, month_data in subscription_monthly_data.items():
            if month_data['month'] == month_display:
                total = month_data['total_revenue']
                break
        total_revenue_data.append(total)

    chart_data['subscription_dynamics']['datasets'].append({
        'label': 'Общая выручка',
        'data': total_revenue_data,
        'borderColor': '#2E7D32',
        'backgroundColor': '#4CAF50',
        'borderWidth': 3,
        'tension': 0.4,
        'fill': False,
        'type': 'line'
    })


    total_revenue = float(financial_stats[1] or 0) if financial_stats else 0
    paid_amount = float(financial_stats[2] or 0) if financial_stats else 0
    total_paid_subscriptions = sum(sub['paid_subscriptions'] for sub in subscription_types_formatted)
    
    context = {
        'employee_name': request.session.get('employee_name'),
        'employee_email': request.session.get('employee_email'),
        
        'start_date_str': start_date_display.strftime('%Y-%m-%d'),
        'end_date_str': end_date_display.strftime('%Y-%m-%d'),


        'registrations': registrations,
        'purchases': purchases,
        

        'financial_stats': financial_stats,
        'total_revenue': total_revenue,
        'paid_amount': paid_amount,
        'daily_revenue': daily_revenue,
        'subscription_payments': subscription_payments,
        

        'subscription_types_data': subscription_types_formatted,
        'subscription_dynamics_data': subscription_monthly_data,
        'total_subscriptions_sold': total_subscriptions_sold,
        'total_subscriptions_revenue_all': total_subscriptions_revenue_all,
        'total_paid_subscriptions': total_paid_subscriptions,


        'chart_data_json': json.dumps(chart_data, ensure_ascii=False),
        'chart_data': chart_data,
        

        'popular_content': popular_content,
        

        'user_activity': user_activity,
        

        'payment_methods': payment_methods,
        

        'genre_stats': genre_stats,
        

        'conversion_stats': conversion_stats,

        'arpu_stats': arpu_stats,
        

        'retention_stats': retention_stats,

        'geography_stats': geography_stats,

        'start_date': start_date_display,
        'end_date': end_date_display,
        'period': period,
        

        'chart_data_json': json.dumps(chart_data, ensure_ascii=False),
        'chart_data': chart_data,
        

        'export_timestamp': datetime.datetime.now().strftime('%Y%m%d_%H%M%S'),

        'has_payment_issues': has_payment_issues,
    }
    
    return render(request, 'employees/analytics/analytics.html', context)

@employee_required
@check_employee_role('ANALYST')
def export_analytics(request):
    """Экспорт аналитики в Excel и HTML"""
    from django.db import connection
    import datetime
    from django.http import HttpResponse
    import io
    import csv
    from django.template.loader import render_to_string
    import json
    

    format_type = request.GET.get('format', 'csv')
    period = request.GET.get('period', '7d')
    
    now = datetime.datetime.now()
    end_date = now
    
    if period == '30d':
        start_date = end_date - datetime.timedelta(days=30)
    elif period == '90d':
        start_date = end_date - datetime.timedelta(days=90)
    elif period == 'all':
        start_date = datetime.datetime(2020, 1, 1)
    else:
        start_date = end_date - datetime.timedelta(days=7)
    
    with connection.cursor() as cursor:


        cursor.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM cinema.users
            WHERE created_at BETWEEN %s AND %s
            GROUP BY DATE(created_at)
            ORDER BY date
        """, [start_date, end_date])
        registrations = cursor.fetchall()

        cursor.execute("""
            SELECT DATE(paid_at) as date, 
                   COUNT(*) as count, 
                   COALESCE(SUM(amount), 0) as amount,
                   status
            FROM cinema.payments
            WHERE paid_at BETWEEN %s AND %s
            GROUP BY DATE(paid_at), status
            ORDER BY date, status
        """, [start_date, end_date])
        payments = cursor.fetchall()
        

        cursor.execute("""
            SELECT DATE(purchased_at) as date, 
                   c.title, c.type, c.price,
                   u.login as user_login
            FROM cinema.purchases p
            JOIN cinema.content c ON c.id = p.content_id
            JOIN cinema.users u ON u.id = p.user_id
            WHERE p.purchased_at BETWEEN %s AND %s
            ORDER BY p.purchased_at DESC
        """, [start_date, end_date])
        purchases_details = cursor.fetchall()
        

        cursor.execute("""
            SELECT 
                sp.name as plan_name,
                us.status,
                us.started_at,
                us.expires_at,
                u.login as user_login,
                COALESCE(p.amount, 0) as payment_amount
            FROM cinema.user_subscriptions us
            JOIN cinema.subscription_plans sp ON sp.id = us.plan_id
            JOIN cinema.users u ON u.id = us.user_id
            LEFT JOIN cinema.payments p ON p.subscription_id = us.id
            WHERE us.started_at BETWEEN %s AND %s
            ORDER BY us.started_at DESC
        """, [start_date, end_date])
        subscriptions = cursor.fetchall()
        

        cursor.execute("""
            SELECT 
                DATE(wh.watched_at) as date,
                u.login,
                c.title as content_title,
                wh.progress_sec
            FROM cinema.watch_history wh
            JOIN cinema.users u ON u.id = wh.user_id
            LEFT JOIN cinema.content c ON c.id = wh.content_id
            WHERE wh.watched_at BETWEEN %s AND %s
            ORDER BY wh.watched_at DESC
            LIMIT 1000
        """, [start_date, end_date])
        user_activity = cursor.fetchall()
        

        cursor.execute("""
            SELECT 
                COUNT(*) as total_payments,
                COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) as total_revenue
            FROM cinema.payments
            WHERE paid_at BETWEEN %s AND %s
        """, [start_date, end_date])
        payment_stats = cursor.fetchone()
        
        cursor.execute("""
            SELECT COUNT(*) as total_users
            FROM cinema.users
            WHERE created_at BETWEEN %s AND %s
        """, [start_date, end_date])
        user_stats = cursor.fetchone()

    if format_type == 'csv':

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')

        writer.writerow(['Отчет аналитики', f'Период: {start_date.date()} - {end_date.date()}', f'Сгенерирован: {datetime.datetime.now().strftime("%d.%m.%Y %H:%M")}'])
        writer.writerow([])

        writer.writerow(['Общая статистика'])
        writer.writerow(['Показатель', 'Значение'])
        writer.writerow(['Всего платежей', payment_stats[0] if payment_stats else 0])
        writer.writerow(['Общая выручка', f'{payment_stats[1] if payment_stats else 0:.2f} ₽'])
        writer.writerow(['Новых пользователей', user_stats[0] if user_stats else 0])
        writer.writerow([])

        writer.writerow(['Регистрации пользователей'])
        writer.writerow(['Дата', 'Количество'])
        for reg in registrations:
            writer.writerow([reg[0], reg[1]])
        writer.writerow([])

        writer.writerow(['Платежи'])
        writer.writerow(['Дата', 'Количество', 'Сумма', 'Статус'])
        for payment in payments:
            writer.writerow([payment[0], payment[1], f'{payment[2]:.2f} ₽', payment[3]])
        writer.writerow([])
        

        writer.writerow(['Покупки контента'])
        writer.writerow(['Дата', 'Пользователь', 'Контент', 'Тип', 'Цена'])
        for purchase in purchases_details:
            writer.writerow([purchase[0], purchase[4], purchase[1], purchase[2], f'{purchase[3]:.2f} ₽'])
        
        output.seek(0)
        

        filename = f'analytics_export_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response = HttpResponse(
            output.getvalue(),
            content_type='text/csv; charset=utf-8-sig'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    

    elif format_type == 'html':

        chart_data = {
            'registrations': [{'date': str(r[0]), 'count': r[1]} for r in registrations],
            'payments': [{'date': str(p[0]), 'amount': float(p[2] or 0)} for p in payments if p[3] == 'paid'],
        }

        html_content = render_to_string('employees/analytics/analytics_export.html', {
            'registrations': registrations,
            'payments': payments,
            'purchases_details': purchases_details,
            'subscriptions': subscriptions,
            'user_activity': user_activity,
            'payment_stats': payment_stats,
            'user_stats': user_stats,
            'chart_data_json': json.dumps(chart_data),
            'start_date': start_date.date(),
            'end_date': (end_date - datetime.timedelta(days=1)).date(),
            'export_date': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
        })
        

        filename = f'analytics_report_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
        response = HttpResponse(html_content, content_type='text/html')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    

    elif format_type == 'excel':
        try:
            import pandas as pd
            import openpyxl
            

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:

                reg_df = pd.DataFrame(registrations, columns=['Дата', 'Регистраций'])
                reg_df.to_excel(writer, sheet_name='Регистрации', index=False)
                

                payments_df = pd.DataFrame(payments, columns=['Дата', 'Кол-во', 'Сумма', 'Статус'])
                payments_df.to_excel(writer, sheet_name='Платежи', index=False)
                

                purchases_df = pd.DataFrame(purchases_details, columns=['Дата', 'Контент', 'Тип', 'Цена', 'Пользователь'])
                purchases_df.to_excel(writer, sheet_name='Покупки', index=False)

                subs_df = pd.DataFrame(subscriptions, columns=['План', 'Статус', 'Начало', 'Окончание', 'Пользователь', 'Оплата'])
                subs_df.to_excel(writer, sheet_name='Подписки', index=False)
                

                activity_df = pd.DataFrame(user_activity, columns=['Дата', 'Пользователь', 'Контент', 'Прогресс (сек)'])
                activity_df.to_excel(writer, sheet_name='Активность', index=False)
            
            output.seek(0)
            
            filename = f'analytics_export_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            response = HttpResponse(
                output.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
        except ImportError:

            return redirect(f'{request.path}?format=csv&period={period}')
    
    return HttpResponse('Неверный формат экспорта')

@employee_required
@check_employee_role('SUPPORT')
def support_panel(request):
    """Панель поддержки"""

    from django.db import connection
    
    with connection.cursor() as cursor:

        cursor.execute("""
            SELECT login, email, created_at 
            FROM cinema.users 
            ORDER BY created_at DESC 
            LIMIT 10
        """)
        recent_users = cursor.fetchall()
        

        cursor.execute("""
            SELECT u.login, us.expires_at, sp.name as plan_name
            FROM cinema.user_subscriptions us
            JOIN cinema.users u ON u.id = us.user_id
            JOIN cinema.subscription_plans sp ON sp.id = us.plan_id
            WHERE us.status = 'active' 
            AND us.expires_at BETWEEN NOW() AND NOW() + INTERVAL '7 days'
            ORDER BY us.expires_at
        """)
        expiring_subscriptions = cursor.fetchall()
    
    return render(request, 'employees/support/support.html', {
        'employee_name': request.session.get('employee_name'),
        'employee_email': request.session.get('employee_email'),
        'recent_users': recent_users,
        'expiring_subscriptions': expiring_subscriptions,
    })

@employee_required
def no_role_panel(request):
    """Панель для сотрудников без назначенных ролей"""
    messages.info(request, 'Вам не назначены права доступа. Обратитесь к администратору.')
    return render(request, 'employees/no_role.html', {
        'employee_name': request.session.get('employee_name'),
        'employee_email': request.session.get('employee_email'),
    })

@employee_required
@check_employee_role('ADMIN')
@employee_required
@check_employee_role('ADMIN')
def admin_subscriptions(request):
    """Список тарифных планов подписок"""
    from django.db import connection
    
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', 'all')
    
    query = """
        SELECT 
            sp.id::text, sp.code, sp.name, sp.period_months, 
            sp.price, sp.is_active, sp.created_at,
            COUNT(us.id) as user_count,
            COALESCE(SUM(CASE WHEN us.status = 'active' THEN 1 ELSE 0 END), 0) as active_count
        FROM cinema.subscription_plans sp
        LEFT JOIN cinema.user_subscriptions us ON us.plan_id = sp.id
    """
    
    where_clauses = []
    params = []
    
    if search_query:
        where_clauses.append("(sp.name ILIKE %s OR sp.code ILIKE %s)")
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    
    if status_filter and status_filter != 'all':
        if status_filter == 'active':
            where_clauses.append("sp.is_active = true")
        elif status_filter == 'inactive':
            where_clauses.append("sp.is_active = false")
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    query += """
        GROUP BY sp.id, sp.code, sp.name, sp.period_months, sp.price, sp.is_active, sp.created_at
        ORDER BY sp.created_at DESC
    """
    
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        plans = []
        for row in cursor.fetchall():
            plans.append(dict(zip(columns, row)))
        
        cursor.execute("SELECT COUNT(*) FROM cinema.subscription_plans")
        total_plans = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cinema.subscription_plans WHERE is_active = true")
        active_plans = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(DISTINCT sp.id) 
            FROM cinema.subscription_plans sp
            JOIN cinema.user_subscriptions us ON us.plan_id = sp.id
        """)
        used_plans = cursor.fetchone()[0]
        
        stats = (total_plans, active_plans, used_plans)
    
    return render(request, 'employees/admin/subscriptions/admin_subscriptions.html', {
        'plans': plans,
        'search_query': search_query,
        'status_filter': status_filter,
        'stats': stats,
        'total_plans': total_plans,
        'active_plans': active_plans,
        'used_plans': used_plans,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_subscription_create(request):
    """Создание нового тарифного плана"""
    from django.db import connection
    from decimal import Decimal
    
    if request.method == 'POST':
        try:
            code = request.POST.get('code', '').strip().upper()
            name = request.POST.get('name', '').strip()
            period_months = int(request.POST.get('period_months', 1))
            price_str = request.POST.get('price', '0')
            description = request.POST.get('description', '').strip()
            is_active = request.POST.get('is_active') == 'on'
            

            if not code or not name:
                messages.error(request, 'Код и название обязательны')
                return redirect('admin_subscription_create')
            
            if period_months not in [1, 3, 6, 12]:
                messages.error(request, 'Период должен быть 1, 3, 6 или 12 месяцев')
                return redirect('admin_subscription_create')
            

            try:
                price_str = price_str.replace(',', '.')
                price = Decimal(price_str).quantize(Decimal('0.01'))
            except:
                price = Decimal('0.00')
            
            if price <= Decimal('0'):
                messages.error(request, 'Цена должна быть больше 0')
                return redirect('admin_subscription_create')
            
            with connection.cursor() as cursor:

                cursor.execute("SELECT 1 FROM cinema.subscription_plans WHERE code = %s", [code])
                if cursor.fetchone():
                    messages.error(request, f'Тариф с кодом "{code}" уже существует')
                    return redirect('admin_subscription_create')

                cursor.execute("""
                    INSERT INTO cinema.subscription_plans 
                    (id, code, name, period_months, price, is_active, created_at)
                    VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, NOW())
                    RETURNING id::text
                """, [code, name, period_months, str(price), is_active])
                
                plan_id = cursor.fetchone()[0]
                messages.success(request, f'Тарифный план "{name}" успешно создан!')
                return redirect('admin_subscriptions')
                
        except Exception as e:
            messages.error(request, f'Ошибка при создании тарифа: {str(e)}')
    
    return render(request, 'employees/admin/subscriptions/admin_subscription_create.html', {
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_subscription_edit(request, plan_id):
    """Редактирование тарифного плана"""
    from django.db import connection
    from decimal import Decimal
    
    if request.method == 'POST':
        try:
            code = request.POST.get('code', '').strip().upper()
            name = request.POST.get('name', '').strip()
            period_months = int(request.POST.get('period_months', 1))
            price_str = request.POST.get('price', '0')
            is_active = request.POST.get('is_active') == 'on'
            
            if not code or not name:
                messages.error(request, 'Код и название обязательны')
                return redirect('admin_subscription_edit', plan_id=plan_id)
            
            if period_months not in [1, 3, 6, 12]:
                messages.error(request, 'Период должен быть 1, 3, 6 или 12 месяцев')
                return redirect('admin_subscription_edit', plan_id=plan_id)
            

            try:
                price_str = price_str.replace(',', '.')
                price = Decimal(price_str).quantize(Decimal('0.01'))
            except:
                price = Decimal('0.00')
            
            if price <= Decimal('0'):
                messages.error(request, 'Цена должна быть больше 0')
                return redirect('admin_subscription_edit', plan_id=plan_id)
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 1 FROM cinema.subscription_plans 
                    WHERE code = %s AND id != %s
                """, [code, plan_id])
                
                if cursor.fetchone():
                    messages.error(request, f'Тариф с кодом "{code}" уже существует')
                    return redirect('admin_subscription_edit', plan_id=plan_id)
                
                cursor.execute("""
                    UPDATE cinema.subscription_plans 
                    SET code = %s, name = %s, period_months = %s, 
                        price = %s, is_active = %s
                    WHERE id = %s
                """, [code, name, period_months, str(price), is_active, plan_id])
                
                messages.success(request, f'Тарифный план "{name}" успешно обновлен!')
                return redirect('admin_subscriptions')
                
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении тарифа: {str(e)}')
    

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                id::text, 
                code, 
                name, 
                period_months, 
                ROUND(price::numeric, 2)::text as price,  -- Преобразуем в строку с округлением
                is_active
            FROM cinema.subscription_plans 
            WHERE id = %s
        """, [plan_id])
        
        plan = cursor.fetchone()
        if not plan:
            messages.error(request, 'Тарифный план не найден')
            return redirect('admin_subscriptions')
        

        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Plan data for edit: {plan}")
        logger.info(f"Price value: {plan[4]}, Type: {type(plan[4])}")
    
    return render(request, 'employees/admin/subscriptions/admin_subscription_edit.html', {
        'plan': {
            'id': plan[0],
            'code': plan[1],
            'name': plan[2],
            'period_months': plan[3],
            'price': plan[4] or '0.00',
            'is_active': plan[5],
        },
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_subscription_delete(request, plan_id):
    """Удаление тарифного плана"""
    from django.db import connection
    
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM cinema.user_subscriptions 
                    WHERE plan_id = %s
                """, [plan_id])
                
                usage_count = cursor.fetchone()[0]
                
                if usage_count > 0:
                    messages.error(request, f'Нельзя удалить тариф, который используется ({usage_count} подписок)')
                    return redirect('admin_subscriptions')

                cursor.execute("SELECT name FROM cinema.subscription_plans WHERE id = %s", [plan_id])
                plan_name = cursor.fetchone()[0]

                cursor.execute("DELETE FROM cinema.subscription_plans WHERE id = %s", [plan_id])
                
                messages.success(request, f'Тарифный план "{plan_name}" удален')
                
        except Exception as e:
            messages.error(request, f'Ошибка при удалении тарифа: {str(e)}')
    
    return redirect('admin_subscriptions')

@employee_required
@check_employee_role('ADMIN')
def admin_subscription_toggle(request, plan_id):
    """Включение/выключение тарифного плана"""
    from django.db import connection
    
    if request.method == 'POST':
        try:
            action = request.POST.get('action', 'toggle')
            
            with connection.cursor() as cursor:
                if action == 'activate':
                    cursor.execute("""
                        UPDATE cinema.subscription_plans 
                        SET is_active = true 
                        WHERE id = %s
                    """, [plan_id])
                    messages.success(request, 'Тарифный план активирован')
                elif action == 'deactivate':
                    cursor.execute("""
                        UPDATE cinema.subscription_plans 
                        SET is_active = false 
                        WHERE id = %s
                    """, [plan_id])
                    messages.success(request, 'Тарифный план деактивирован')
                else:

                    cursor.execute("""
                        UPDATE cinema.subscription_plans 
                        SET is_active = NOT is_active 
                        WHERE id = %s
                        RETURNING is_active
                    """, [plan_id])
                    new_status = cursor.fetchone()[0]
                    status_text = "активирован" if new_status else "деактивирован"
                    messages.success(request, f'Тарифный план {status_text}')
                    
        except Exception as e:
            messages.error(request, f'Ошибка: {str(e)}')
    
    return redirect('admin_subscriptions')

@employee_required
@check_employee_role('ADMIN')
def admin_user_subscriptions(request):
    """Управление пользовательскими подписками"""
    from django.db import connection
    import datetime
    

    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', 'all')
    plan_filter = request.GET.get('plan', 'all')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    

    query = """
        SELECT 
            us.id::text, us.user_id::text, us.plan_id::text,
            us.status, us.started_at, us.expires_at,
            u.login as user_login, u.email as user_email,
            sp.name as plan_name, sp.code as plan_code,
            p.amount as payment_amount, p.paid_at,
            CASE 
                WHEN us.status != 'active' THEN us.status
                WHEN us.expires_at IS NULL THEN 'active'
                WHEN us.expires_at > NOW() THEN 'active'
                ELSE 'expired'
            END as actual_status
        FROM cinema.user_subscriptions us
        JOIN cinema.users u ON u.id = us.user_id
        JOIN cinema.subscription_plans sp ON sp.id = us.plan_id
        LEFT JOIN cinema.payments p ON p.subscription_id = us.id
    """
    
    where_clauses = []
    params = []
    
    if search_query:
        where_clauses.append("(u.login ILIKE %s OR u.email ILIKE %s)")
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    
    if status_filter and status_filter != 'all':
        if status_filter == 'expired':
            where_clauses.append("(us.expires_at < NOW() AND us.status = 'active')")
        elif status_filter == 'future':
            where_clauses.append("us.started_at > NOW()")
        else:
            where_clauses.append("us.status = %s")
            params.append(status_filter)
    
    if plan_filter and plan_filter != 'all':
        where_clauses.append("sp.id = %s")
        params.append(plan_filter)
    
    if date_from:
        where_clauses.append("DATE(us.started_at) >= %s")
        params.append(date_from)
    
    if date_to:
        where_clauses.append("DATE(us.started_at) <= %s") 
        params.append(date_to)
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    query += " ORDER BY us.started_at DESC"
    
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        subscriptions = []
        for row in cursor.fetchall():
            subscriptions.append(dict(zip(columns, row)))
        

        cursor.execute("""
            SELECT id::text, name, code 
            FROM cinema.subscription_plans 
            WHERE is_active = true 
            ORDER BY name
        """)
        active_plans = cursor.fetchall()
        

        cursor.execute("SELECT COUNT(*) FROM cinema.user_subscriptions")
        total = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT COUNT(*) FROM cinema.user_subscriptions 
            WHERE status = 'active' 
            AND (expires_at IS NULL OR expires_at > NOW())
        """)
        active = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT COUNT(*) FROM cinema.user_subscriptions 
            WHERE status = 'active' AND expires_at < NOW()
        """)
        expired = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT COUNT(*) FROM cinema.user_subscriptions 
            WHERE status = 'cancelled'
        """)
        cancelled = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT COUNT(*) FROM cinema.user_subscriptions 
            WHERE started_at > NOW()
        """)
        future = cursor.fetchone()[0] or 0
        
        stats = (total, active, expired, cancelled, future)
    
    return render(request, 'employees/admin/subscriptions/admin_user_subscriptions.html', {
        'subscriptions': subscriptions,
        'active_plans': active_plans,
        'search_query': search_query,
        'status_filter': status_filter,
        'plan_filter': plan_filter,
        'date_from': date_from,
        'date_to': date_to,
        'stats': stats,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_grant_subscription(request):
    """Выдача подписки пользователю"""
    from django.db import connection
    import datetime
    
    if request.method == 'POST':
        try:
            user_id = request.POST.get('user_id', '').strip()
            plan_id = request.POST.get('plan_id')
            start_date = request.POST.get('start_date', '')
            status = request.POST.get('status', 'active')
            
            if not user_id or not plan_id:
                messages.error(request, 'Укажите пользователя и тарифный план')
                return redirect('admin_grant_subscription')
            

            if start_date:
                started_at = datetime.datetime.strptime(start_date, '%Y-%m-%d')
            else:
                started_at = datetime.datetime.now()
            
            with connection.cursor() as cursor:

                cursor.execute("""
                    SELECT period_months, name FROM cinema.subscription_plans 
                    WHERE id = %s
                """, [plan_id])
                
                plan_info = cursor.fetchone()
                if not plan_info:
                    messages.error(request, 'Тарифный план не найден')
                    return redirect('admin_grant_subscription')
                
                period_months, plan_name = plan_info
                expires_at = started_at + datetime.timedelta(days=period_months * 30)
                

                cursor.execute("SELECT login FROM cinema.users WHERE id = %s", [user_id])
                user_info = cursor.fetchone()
                if not user_info:
                    messages.error(request, 'Пользователь не найден')
                    return redirect('admin_grant_subscription')
                
                user_login = user_info[0]
                

                cursor.execute("""
                    SELECT id, status, expires_at 
                    FROM cinema.user_subscriptions 
                    WHERE user_id = %s AND plan_id = %s AND started_at = %s
                """, [user_id, plan_id, started_at])
                
                existing_sub = cursor.fetchone()
                
                if existing_sub:

                    sub_id, sub_status, sub_expires = existing_sub
                    

                    messages.warning(request, 
                        f'У пользователя {user_login} уже есть подписка "{plan_name}" на эту дату. '
                        f'Вы можете обновить существующую подписку.')

                    return redirect('admin_user_subscription_edit', sub_id=sub_id)

                cursor.execute("""
                    SELECT id, expires_at, status
                    FROM cinema.user_subscriptions 
                    WHERE user_id = %s AND plan_id = %s 
                    AND status = 'active'
                    ORDER BY started_at DESC
                    LIMIT 1
                """, [user_id, plan_id])
                
                active_sub = cursor.fetchone()
                
                if active_sub:
                    active_id, active_expires, active_status = active_sub
                    if active_expires and active_expires > started_at:

                        messages.warning(request,
                            f'У пользователя {user_login} уже есть активная подписка "{plan_name}" '
                            f'до {active_expires.date()}. '
                            f'Вы можете продлить существующую подписку.')
                        return redirect('admin_user_subscription_edit', sub_id=active_id)
                

                cursor.execute("""
                    INSERT INTO cinema.user_subscriptions 
                    (id, user_id, plan_id, status, started_at, expires_at)
                    VALUES (gen_random_uuid(), %s, %s, %s, %s, %s)
                    RETURNING id::text
                """, [user_id, plan_id, status, started_at, expires_at])
                
                new_sub_id = cursor.fetchone()[0]
                
                messages.success(request, 
                    f'Подписка "{plan_name}" успешно выдана пользователю {user_login}')
                return redirect('admin_user_subscriptions')
                
        except Exception as e:
            messages.error(request, f'Ошибка при выдаче подписки: {str(e)}')
    

    with connection.cursor() as cursor:

        cursor.execute("""
            SELECT id::text, login, email 
            FROM cinema.users 
            WHERE is_active = true
            ORDER BY login
            LIMIT 100
        """)
        users = cursor.fetchall()

        cursor.execute("""
            SELECT id::text, name, code, price::text, period_months 
            FROM cinema.subscription_plans 
            WHERE is_active = true 
            ORDER BY name
        """)
        plans = cursor.fetchall()
    
    return render(request, 'employees/admin/subscriptions/admin_grant_subscription.html', {
        'users': users,
        'plans': plans,
        'today': datetime.date.today(),
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_user_subscription_edit(request, sub_id):
    """Редактирование пользовательской подписки"""
    from django.db import connection
    import datetime
    
    if request.method == 'POST':
        try:
            status = request.POST.get('status')
            expires_at_str = request.POST.get('expires_at', '')
            
            if not status:
                messages.error(request, 'Укажите статус подписки')
                return redirect('admin_user_subscription_edit', sub_id=sub_id)
            
            expires_at = None
            if expires_at_str:
                expires_at = datetime.datetime.strptime(expires_at_str, '%Y-%m-%d')
            
            with connection.cursor() as cursor:

                cursor.execute("""
                    UPDATE cinema.user_subscriptions 
                    SET status = %s, expires_at = %s
                    WHERE id = %s
                """, [status, expires_at, sub_id])
                
                messages.success(request, 'Подписка обновлена')
                return redirect('admin_user_subscriptions')
                
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении подписки: {str(e)}')

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                us.id::text, us.user_id::text, us.plan_id::text,
                us.status, us.started_at, us.expires_at,
                u.login as user_login,
                sp.name as plan_name
            FROM cinema.user_subscriptions us
            JOIN cinema.users u ON u.id = us.user_id
            JOIN cinema.subscription_plans sp ON sp.id = us.plan_id
            WHERE us.id = %s
        """, [sub_id])
        
        subscription = cursor.fetchone()
        if not subscription:
            messages.error(request, 'Подписка не найдена')
            return redirect('admin_user_subscriptions')
    
    return render(request, 'employees/admin/subscriptions/admin_user_subscription_edit.html', {
        'subscription': {
            'id': subscription[0],
            'user_id': subscription[1],
            'plan_id': subscription[2],
            'status': subscription[3],
            'started_at': subscription[4],
            'expires_at': subscription[5],
            'user_login': subscription[6],
            'plan_name': subscription[7],
        },
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_user_subscription_delete(request, sub_id):
    """Удаление пользовательской подписки"""
    from django.db import connection
    
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM cinema.user_subscriptions WHERE id = %s", [sub_id])
                messages.success(request, 'Подписка удалена')
        except Exception as e:
            messages.error(request, f'Ошибка при удалении подписки: {str(e)}')
    
    return redirect('admin_user_subscriptions')

@employee_required
@check_employee_role('ADMIN')
def admin_user_subscription_extend(request, sub_id):
    """Продление пользовательской подписки"""
    from django.db import connection
    import datetime
    
    if request.method == 'POST':
        try:
            months_to_add = int(request.POST.get('months', 1))
            
            with connection.cursor() as cursor:
 
                cursor.execute("""
                    SELECT us.expires_at, us.started_at, us.user_id, us.plan_id,
                           u.login, sp.name
                    FROM cinema.user_subscriptions us
                    JOIN cinema.users u ON u.id = us.user_id
                    LEFT JOIN cinema.subscription_plans sp ON sp.id = us.plan_id
                    WHERE us.id = %s
                """, [sub_id])
                
                result = cursor.fetchone()
                if not result:
                    messages.error(request, 'Подписка не найдена')
                    return redirect('admin_user_subscriptions')
                
                expires_at, started_at, user_id, plan_id, user_login, plan_name = result

                if expires_at:
                    new_expires_at = expires_at + datetime.timedelta(days=months_to_add * 30)
                else:
                    new_expires_at = datetime.datetime.now() + datetime.timedelta(days=months_to_add * 30)

                cursor.execute("""
                    UPDATE cinema.user_subscriptions 
                    SET expires_at = %s, status = 'active'
                    WHERE id = %s
                """, [new_expires_at, sub_id])
                
                messages.success(request, 
                    f'Подписка "{plan_name}" пользователя {user_login} продлена на {months_to_add} месяцев')
                return redirect('admin_user_subscriptions')
                
        except Exception as e:
            messages.error(request, f'Ошибка при продлении подписки: {str(e)}')
    

    return redirect('admin_user_subscriptions')

@employee_required
@check_employee_role('ADMIN')
def admin_payments(request):
    """Управление платежами"""
    from django.db import connection
    import datetime

    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', 'all')
    type_filter = request.GET.get('type', 'all')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    query = """
        SELECT 
            p.id::text, p.txn_uuid, p.amount::text, p.status,
            p.paid_at, p.created_at, p.purchase_id::text, p.subscription_id::text,
            u.login as user_login, u.email as user_email,
            sp.name as subscription_name,
            c.title as content_title,
            CASE 
                WHEN p.subscription_id IS NOT NULL THEN 'subscription'
                WHEN p.purchase_id IS NOT NULL THEN 'purchase'
                ELSE 'other'
            END as payment_type
        FROM cinema.payments p
        LEFT JOIN cinema.users u ON (
            u.id = (SELECT user_id FROM cinema.user_subscriptions WHERE id = p.subscription_id)
            OR u.id = (SELECT user_id FROM cinema.purchases WHERE id = p.purchase_id)
        )
        LEFT JOIN cinema.user_subscriptions us ON us.id = p.subscription_id
        LEFT JOIN cinema.subscription_plans sp ON sp.id = us.plan_id
        LEFT JOIN cinema.purchases pur ON pur.id = p.purchase_id
        LEFT JOIN cinema.content c ON c.id = pur.content_id
    """
    
    where_clauses = []
    params = []
    
    if search_query:
        where_clauses.append("""
            (u.login ILIKE %s OR u.email ILIKE %s 
             OR p.txn_uuid ILIKE %s OR c.title ILIKE %s)
        """)
        params.extend([f'%{search_query}%', f'%{search_query}%', 
                      f'%{search_query}%', f'%{search_query}%'])
    
    if status_filter and status_filter != 'all':
        where_clauses.append("p.status = %s")
        params.append(status_filter)
    
    if type_filter and type_filter != 'all':
        if type_filter == 'subscription':
            where_clauses.append("p.subscription_id IS NOT NULL")
        elif type_filter == 'purchase':
            where_clauses.append("p.purchase_id IS NOT NULL")
    
    if date_from:
        where_clauses.append("DATE(p.created_at) >= %s")
        params.append(date_from)
    
    if date_to:
        where_clauses.append("DATE(p.created_at) <= %s")
        params.append(date_to)
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    query += " ORDER BY p.created_at DESC"
    
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        payments = []
        for row in cursor.fetchall():
            payments.append(dict(zip(columns, row)))
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COALESCE(SUM(amount), 0) as total_amount,
                COUNT(CASE WHEN status = 'paid' THEN 1 END) as paid_count,
                COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) as paid_amount,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_count,
                COUNT(CASE WHEN status = 'cancelled' THEN 1 END) as cancelled_count
            FROM cinema.payments
        """)
        stats = cursor.fetchone()
    
    return render(request, 'employees/admin/subscriptions/admin_payments.html', {
        'payments': payments,
        'search_query': search_query,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'date_from': date_from,
        'date_to': date_to,
        'stats': stats,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_payment_update(request, payment_id):
    """Обновление статуса платежа"""
    from django.db import connection
    
    if request.method == 'POST':
        try:
            status = request.POST.get('status')
            paid_at_str = request.POST.get('paid_at', '')
            
            if not status:
                messages.error(request, 'Укажите статус платежа')
                return redirect('admin_payments')
            
            paid_at = None
            if paid_at_str:
                from datetime import datetime
                paid_at = datetime.strptime(paid_at_str, '%Y-%m-%d %H:%M:%S')
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE cinema.payments 
                    SET status = %s, paid_at = %s 
                    WHERE id = %s
                """, [status, paid_at, payment_id])
                
                messages.success(request, 'Статус платежа обновлен')
                
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении платежа: {str(e)}')
    
    return redirect('admin_payments')

@employee_required
@check_employee_role('ADMIN')
def export_subscriptions(request):
    """Экспорт подписок в CSV"""
    from django.db import connection
    import io
    import csv
    import datetime
    from django.http import HttpResponse
    
    format_type = request.GET.get('format', 'csv')
    export_type = request.GET.get('type', 'all')
    
    with connection.cursor() as cursor:
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        
        if export_type == 'plans' or export_type == 'all':
            cursor.execute("""
                SELECT code, name, period_months, price, is_active, created_at
                FROM cinema.subscription_plans
                ORDER BY created_at
            """)
            plans = cursor.fetchall()
            
            writer.writerow(['=== ТАРИФНЫЕ ПЛАНЫ ==='])
            writer.writerow(['Код', 'Название', 'Период (мес)', 'Цена', 'Активен', 'Создан'])
            for plan in plans:
                writer.writerow(plan)
            writer.writerow([])
        
        if export_type == 'user_subs' or export_type == 'all':
            cursor.execute("""
                SELECT 
                    u.login, u.email, sp.name, us.status,
                    us.started_at, us.expires_at, us.created_at
                FROM cinema.user_subscriptions us
                JOIN cinema.users u ON u.id = us.user_id
                JOIN cinema.subscription_plans sp ON sp.id = us.plan_id
                ORDER BY us.created_at DESC
            """)
            user_subs = cursor.fetchall()
            
            writer.writerow(['=== ПОЛЬЗОВАТЕЛЬСКИЕ ПОДПИСКИ ==='])
            writer.writerow(['Логин', 'Email', 'Тариф', 'Статус', 'Начало', 'Окончание', 'Создана'])
            for sub in user_subs:
                writer.writerow(sub)
            writer.writerow([])
        
        if export_type == 'payments' or export_type == 'all':
            cursor.execute("""
                SELECT 
                    p.txn_uuid, p.amount, p.status, p.paid_at,
                    u.login, sp.name as subscription_name,
                    c.title as content_title
                FROM cinema.payments p
                LEFT JOIN cinema.users u ON (
                    u.id = (SELECT user_id FROM cinema.user_subscriptions WHERE id = p.subscription_id)
                    OR u.id = (SELECT user_id FROM cinema.purchases WHERE id = p.purchase_id)
                )
                LEFT JOIN cinema.user_subscriptions us ON us.id = p.subscription_id
                LEFT JOIN cinema.subscription_plans sp ON sp.id = us.plan_id
                LEFT JOIN cinema.purchases pur ON pur.id = p.purchase_id
                LEFT JOIN cinema.content c ON c.id = pur.content_id
                ORDER BY p.created_at DESC
            """)
            payments = cursor.fetchall()
            
            writer.writerow(['=== ПЛАТЕЖИ ==='])
            writer.writerow(['ID транзакции', 'Сумма', 'Статус', 'Оплачен', 'Пользователь', 'Подписка', 'Контент'])
            for payment in payments:
                writer.writerow(payment)
        
        output.seek(0)
        
        filename = f'subscriptions_export_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response = HttpResponse(
            output.getvalue(),
            content_type='text/csv; charset=utf-8-sig'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response



@employee_required
@check_employee_role('ADMIN')
def admin_users_list(request):
    """Список пользователей"""
    from django.db import connection
    import logging
    
    logger = logging.getLogger(__name__)
    
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', 'all')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    query = """
        SELECT 
            u.id::text, u.email, u.login, 
            u.avatar_url, u.is_active, u.created_at, u.updated_at,
            STRING_AGG(DISTINCT r.code, ', ') as roles,
            COUNT(DISTINCT pur.id) as purchase_count,
            COUNT(DISTINCT us.id) as subscription_count
        FROM cinema.users u
        LEFT JOIN cinema.user_roles ur ON ur.user_id = u.id
        LEFT JOIN cinema.roles r ON r.id = ur.role_id
        LEFT JOIN cinema.purchases pur ON pur.user_id = u.id
        LEFT JOIN cinema.user_subscriptions us ON us.user_id = u.id
    """
    
    where_clauses = []
    params = []
    
    if search_query:
        where_clauses.append("""
            (u.email ILIKE %s OR u.login ILIKE %s 
             OR u.id::text ILIKE %s)
        """)
        params.extend([f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'])
    
    if status_filter and status_filter != 'all':
        if status_filter == 'active':
            where_clauses.append("u.is_active = true")
        elif status_filter == 'inactive':
            where_clauses.append("u.is_active = false")
    
    if date_from:
        where_clauses.append("DATE(u.created_at) >= %s")
        params.append(date_from)
    
    if date_to:
        where_clauses.append("DATE(u.created_at) <= %s")
        params.append(date_to)
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    query += """
        GROUP BY u.id, u.email, u.login, u.avatar_url, 
                 u.is_active, u.created_at, u.updated_at
        ORDER BY u.created_at DESC
    """
    
    logger.debug(f"User list query: {query}")
    logger.debug(f"Params: {params}")
    
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        users = []
        for row in cursor.fetchall():
            users.append(dict(zip(columns, row)))
        
 
        cursor.execute("SELECT COUNT(*) FROM cinema.users")
        total_users = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM cinema.users WHERE is_active = true")
        active_users = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM cinema.users WHERE is_active = false")
        inactive_users = cursor.fetchone()[0] or 0

        cursor.execute("SELECT id::text, code, name FROM cinema.roles ORDER BY name")
        all_roles = cursor.fetchall()
        
        stats = (total_users, active_users, inactive_users)
    
    return render(request, 'employees/admin/users/admin_users_list.html', {
        'users': users,
        'all_roles': all_roles,
        'search_query': search_query,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'stats': stats,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_user_create(request):
    """Создание нового пользователя"""
    from django.db import connection
    from django.contrib.auth.hashers import make_password
    from django.contrib.auth.models import User
    import uuid
    
    if request.method == 'POST':
        try:
            email = request.POST.get('email', '').strip()
            login = request.POST.get('login', '').strip()
            password = request.POST.get('password', '')
            confirm_password = request.POST.get('confirm_password', '')
            is_active = request.POST.get('is_active') == 'on'
            avatar_url = request.POST.get('avatar_url', '').strip()
            roles = request.POST.getlist('roles', [])
            
            if not email or not login:
                messages.error(request, 'Email и логин обязательны')
                return redirect('admin_user_create')
            
            if not password:
                messages.error(request, 'Пароль обязателен')
                return redirect('admin_user_create')
            
            if password != confirm_password:
                messages.error(request, 'Пароли не совпадают')
                return redirect('admin_user_create')
            
            if len(password) < 6:
                messages.error(request, 'Пароль должен содержать минимум 6 символов')
                return redirect('admin_user_create')
            
            if User.objects.filter(username__iexact=login).exists():
                messages.error(request, 'Такой логин уже занят в системе входа')
                return redirect('admin_user_create')
            
            if User.objects.filter(email__iexact=email).exists():
                messages.error(request, 'Такой email уже используется в системе входа')
                return redirect('admin_user_create')
            
            password_hash = make_password(password)
            
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM cinema.users WHERE email = %s OR login = %s", [email, login])
                if cursor.fetchone():
                    messages.error(request, 'Пользователь с таким email или логином уже существует')
                    return redirect('admin_user_create')
            
            django_user = User.objects.create_user(
                username=login,
                email=email,
                password=password,
                is_active=is_active
            )
            django_user.save()
            
            with connection.cursor() as cursor:

                avatar_url_value = None
                if avatar_url and avatar_url != '':
                    if avatar_url.startswith(('http://', 'https://')) and len(avatar_url) <= 2048:
                        avatar_url_value = avatar_url
                
                user_id = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO cinema.users 
                    (id, email, login, password_hash, avatar_url, is_active, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                    RETURNING id
                """, [user_id, email, login, password_hash, avatar_url_value, is_active])
                
                cinema_user_id = cursor.fetchone()[0]
                
                for role_id in roles:
                    cursor.execute("""
                        INSERT INTO cinema.user_roles (user_id, role_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                    """, [cinema_user_id, role_id])
            
            messages.success(request, f'Пользователь {login} ({email}) успешно создан! Можно входить на сайт.')
            return redirect('admin_users_list')
                
        except Exception as e:
            messages.error(request, f'Ошибка при создании пользователя: {str(e)}')
            logger.error(f"Error creating user: {e}")
            import traceback
            traceback.print_exc()
    
    with connection.cursor() as cursor:
        cursor.execute("SELECT id::text, code, name FROM cinema.roles ORDER BY name")
        all_roles = cursor.fetchall()
    
    return render(request, 'employees/admin/users/admin_user_create.html', {
        'all_roles': all_roles,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_user_edit(request, user_id):
    """Редактирование пользователя"""
    from django.db import connection
    from django.contrib.auth.hashers import make_password
    from django.contrib.auth.models import User
    
    if request.method == 'POST':
        try:
            email = request.POST.get('email', '').strip()
            login = request.POST.get('login', '').strip()
            password = request.POST.get('password', '').strip()
            is_active = request.POST.get('is_active') == 'on'
            avatar_url = request.POST.get('avatar_url', '').strip()
            roles = request.POST.getlist('roles', [])
            
            if not email or not login:
                messages.error(request, 'Email и логин обязательны')
                return redirect('admin_user_edit', user_id=user_id)

            with connection.cursor() as cursor:
                cursor.execute("SELECT login FROM cinema.users WHERE id = %s", [user_id])
                old_login_result = cursor.fetchone()
                if not old_login_result:
                    messages.error(request, 'Пользователь не найден')
                    return redirect('admin_users_list')
                old_login = old_login_result[0]
            
            django_user = User.objects.filter(username__iexact=login).exclude(username__iexact=old_login).first()
            if django_user:
                messages.error(request, 'Такой логин уже занят в системе входа')
                return redirect('admin_user_edit', user_id=user_id)
            
            django_user_email = User.objects.filter(email__iexact=email).exclude(username__iexact=old_login).first()
            if django_user_email:
                messages.error(request, 'Такой email уже используется в системе входа')
                return redirect('admin_user_edit', user_id=user_id)
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 1 FROM cinema.users 
                    WHERE (email = %s OR login = %s) AND id != %s
                """, [email, login, user_id])
                
                if cursor.fetchone():
                    messages.error(request, 'Пользователь с таким email или логином уже существует')
                    return redirect('admin_user_edit', user_id=user_id)

            django_user = User.objects.filter(username=old_login).first()
            if django_user:
                django_user.username = login
                django_user.email = email
                django_user.is_active = is_active
                if password:
                    django_user.set_password(password)
                django_user.save()
            else:
                django_user = User.objects.create_user(
                    username=login,
                    email=email,
                    password=password if password else 'temporary123',
                    is_active=is_active
                )
                messages.warning(request, f'Создан новый аккаунт для входа. Установите пароль.')

            with connection.cursor() as cursor:
                avatar_url_value = None
                if avatar_url and avatar_url != '':
                    if avatar_url.startswith(('http://', 'https://')) and len(avatar_url) <= 2048:
                        avatar_url_value = avatar_url

                if password:
                    password_hash = make_password(password)
                    cursor.execute("""
                        UPDATE cinema.users 
                        SET email = %s, login = %s, password_hash = %s, 
                            is_active = %s, avatar_url = %s, updated_at = NOW()
                        WHERE id = %s
                    """, [email, login, password_hash, is_active, avatar_url_value, user_id])
                else:
                    cursor.execute("""
                        UPDATE cinema.users 
                        SET email = %s, login = %s, is_active = %s, 
                            avatar_url = %s, updated_at = NOW()
                        WHERE id = %s
                    """, [email, login, is_active, avatar_url_value, user_id])
                

                cursor.execute("DELETE FROM cinema.user_roles WHERE user_id = %s", [user_id])
                for role_id in roles:
                    cursor.execute("""
                        INSERT INTO cinema.user_roles (user_id, role_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                    """, [user_id, role_id])
                
                messages.success(request, f'Пользователь {login} успешно обновлен в обеих системах!')
                return redirect('admin_users_list')
                
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении пользователя: {str(e)}')
            logger.error(f"Error updating user {user_id}: {e}")
            import traceback
            traceback.print_exc()
    
    with connection.cursor() as cursor:

        cursor.execute("""
            SELECT 
                id::text, email, login, avatar_url, 
                is_active, created_at, updated_at
            FROM cinema.users 
            WHERE id = %s
        """, [user_id])
        
        user = cursor.fetchone()
        if not user:
            messages.error(request, 'Пользователь не найден')
            return redirect('admin_users_list')

        cursor.execute("""
            SELECT role_id::text
            FROM cinema.user_roles 
            WHERE user_id = %s
        """, [user_id])
        user_roles = [row[0] for row in cursor.fetchall()]
        

        cursor.execute("SELECT id::text, code, name FROM cinema.roles ORDER BY name")
        all_roles = cursor.fetchall()

        cursor.execute("""
            SELECT 
                COUNT(DISTINCT pur.id) as purchase_count,
                COUNT(DISTINCT us.id) as subscription_count,
                COUNT(DISTINCT wh.id) as watch_count,
                COUNT(DISTINCT fav.content_id) as favorite_count
            FROM cinema.users u
            LEFT JOIN cinema.purchases pur ON pur.user_id = u.id
            LEFT JOIN cinema.user_subscriptions us ON us.user_id = u.id
            LEFT JOIN cinema.watch_history wh ON wh.user_id = u.id
            LEFT JOIN cinema.favorites fav ON fav.user_id = u.id
            WHERE u.id = %s
            GROUP BY u.id
        """, [user_id])
        stats_result = cursor.fetchone()
        user_stats = stats_result if stats_result else (0, 0, 0, 0)

    context = {
        'user': {
            'id': user[0],
            'email': user[1],
            'login': user[2],
            'avatar_url': user[3] or '',
            'is_active': user[4],
            'created_at': user[5],
            'updated_at': user[6],
        },
        'user_roles': user_roles,
        'all_roles': all_roles,
        'user_stats': user_stats,
        'employee_name': request.session.get('employee_name'),
    }
    
    return render(request, 'employees/admin/users/admin_user_edit.html', context)

@employee_required
@check_employee_role('ADMIN')
def admin_user_delete(request, user_id):
    """Удаление пользователя с очисткой всех связанных данных"""
    from django.db import connection
    
    if request.method == 'POST':
        try:
            action = request.POST.get('action', 'delete')
            
            with connection.cursor() as cursor:
                cursor.execute("SELECT login, email FROM cinema.users WHERE id = %s", [user_id])
                user_info = cursor.fetchone()
                
                if user_info:
                    user_login, user_email = user_info
                    
                    if action == 'deactivate':
                        cursor.execute("""
                            UPDATE cinema.users 
                            SET is_active = false, updated_at = NOW()
                            WHERE id = %s
                        """, [user_id])
                        messages.success(request, f'Пользователь {user_login} деактивирован')
                    
                    elif action == 'delete_force':
                        try:
                            cursor.execute("""
                                DELETE FROM cinema.payments 
                                WHERE subscription_id IN (
                                    SELECT id FROM cinema.user_subscriptions WHERE user_id = %s
                                )
                            """, [user_id])
                            
                            cursor.execute("DELETE FROM cinema.user_subscriptions WHERE user_id = %s", [user_id])
                            
                            cursor.execute("""
                                DELETE FROM cinema.payments 
                                WHERE purchase_id IN (
                                    SELECT id FROM cinema.purchases WHERE user_id = %s
                                )
                            """, [user_id])

                            cursor.execute("DELETE FROM cinema.purchases WHERE user_id = %s", [user_id])
                            
                            cursor.execute("DELETE FROM cinema.watch_history WHERE user_id = %s", [user_id])
                            
                            cursor.execute("DELETE FROM cinema.favorites WHERE user_id = %s", [user_id])
                            
                            cursor.execute("""
                                DELETE FROM cinema.playlist_items 
                                WHERE playlist_id IN (
                                    SELECT id FROM cinema.playlists WHERE user_id = %s
                                )
                            """, [user_id])
                            cursor.execute("DELETE FROM cinema.playlists WHERE user_id = %s", [user_id])
                            
                            cursor.execute("DELETE FROM cinema.content_reviews WHERE user_id = %s", [user_id])
                            
                            cursor.execute("DELETE FROM cinema.watchlist WHERE user_id = %s", [user_id])
                            
                            cursor.execute("DELETE FROM cinema.user_roles WHERE user_id = %s", [user_id])
                            
                            cursor.execute("""
                                DELETE FROM cinema.ticket_messages 
                                WHERE ticket_id IN (
                                    SELECT id FROM cinema.support_tickets WHERE user_id = %s
                                )
                            """, [user_id])
                            cursor.execute("DELETE FROM cinema.support_tickets WHERE user_id = %s", [user_id])
                            
                            cursor.execute("DELETE FROM cinema.users WHERE id = %s", [user_id])

                            try:
                                from django.contrib.auth.models import User
                                django_user = User.objects.filter(email=user_email).first()
                                if django_user:
                                    django_user.delete()
                            except Exception as e:
                                logger.error(f"Error deleting Django user {user_email}: {e}")
                            
                            messages.success(request, 
                                f'Пользователь {user_login} ({user_email}) полностью удален. '
                                f'Можно регистрироваться с этой почтой заново.')
                            
                        except Exception as delete_error:
                            logger.error(f"Error deleting user {user_id}: {delete_error}")
                            messages.error(request, 
                                f'Ошибка при удалении пользователя: {str(delete_error)}. '
                                f'Возможно, есть дополнительные связи в базе данных.')
                            return redirect('admin_users_list')
                    
                    else:
                        cursor.execute("""
                            SELECT 
                                (SELECT COUNT(*) FROM cinema.purchases WHERE user_id = %s) as purchase_count,
                                (SELECT COUNT(*) FROM cinema.user_subscriptions WHERE user_id = %s) as subscription_count,
                                (SELECT COUNT(*) FROM cinema.content_reviews WHERE user_id = %s) as review_count
                        """, [user_id, user_id, user_id])
                        
                        dependencies = cursor.fetchone()
                        purchase_count, subscription_count, review_count = dependencies
                        
                        total_dependencies = (purchase_count or 0) + (subscription_count or 0) + (review_count or 0)
                        
                        if total_dependencies > 0:
                            cursor.execute("""
                                UPDATE cinema.users 
                                SET is_active = false, updated_at = NOW()
                                WHERE id = %s
                            """, [user_id])
                            messages.warning(request, 
                                f'Пользователь {user_login} имеет {total_dependencies} зависимостей. '
                                f'Аккаунт деактивирован вместо удаления.')
                        else:
                            cursor.execute("DELETE FROM cinema.users WHERE id = %s", [user_id])
                            
                            try:
                                from django.contrib.auth.models import User
                                django_user = User.objects.filter(email=user_email).first()
                                if django_user:
                                    django_user.delete()
                            except Exception as e:
                                logger.error(f"Error deleting Django user {user_email}: {e}")
                            
                            messages.success(request, f'Пользователь {user_login} ({user_email}) удален')
                else:
                    messages.error(request, 'Пользователь не найден')
                    
        except Exception as e:
            messages.error(request, f'Ошибка при удалении пользователя: {str(e)}')
            logger.error(f"Error deleting user {user_id}: {e}")
    
    return redirect('admin_users_list')

@employee_required
@check_employee_role('ADMIN')
def admin_user_toggle_status(request, user_id):
    """Активация/деактивация пользователя"""
    from django.db import connection
    
    if request.method == 'POST':
        try:
            action = request.POST.get('action', 'toggle')
            
            with connection.cursor() as cursor:
                cursor.execute("SELECT login, is_active FROM cinema.users WHERE id = %s", [user_id])
                user_info = cursor.fetchone()
                
                if user_info:
                    user_login, is_active = user_info
                    
                    if action == 'activate':
                        cursor.execute("""
                            UPDATE cinema.users 
                            SET is_active = true, updated_at = NOW()
                            WHERE id = %s
                        """, [user_id])
                        messages.success(request, f'Пользователь {user_login} активирован')
                    elif action == 'deactivate':
                        cursor.execute("""
                            UPDATE cinema.users 
                            SET is_active = false, updated_at = NOW()
                            WHERE id = %s
                        """, [user_id])
                        messages.success(request, f'Пользователь {user_login} деактивирован')
                    else:
                        new_status = not is_active
                        cursor.execute("""
                            UPDATE cinema.users 
                            SET is_active = %s, updated_at = NOW()
                            WHERE id = %s
                        """, [new_status, user_id])
                        
                        status_text = "активирован" if new_status else "деактивирован"
                        messages.success(request, f'Пользователь {user_login} {status_text}')
                else:
                    messages.error(request, 'Пользователь не найден')
                    
        except Exception as e:
            messages.error(request, f'Ошибка: {str(e)}')
            logger.error(f"Error toggling user status {user_id}: {e}")
    
    return redirect('admin_users_list')

@employee_required
@check_employee_role('ADMIN')
def admin_user_reset_password(request, user_id):
    """Сброс пароля пользователя"""
    from django.db import connection
    from django.contrib.auth.hashers import make_password
    import secrets
    import string
    
    if request.method == 'POST':
        try:
            alphabet = string.ascii_letters + string.digits
            new_password = ''.join(secrets.choice(alphabet) for _ in range(12))
            
            password_hash = make_password(new_password)
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE cinema.users 
                    SET password_hash = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING login, email
                """, [password_hash, user_id])
                
                result = cursor.fetchone()
                if result:
                    user_login, user_email = result

                    messages.success(request, 
                        f'Пароль пользователя {user_login} сброшен! Новый пароль: {new_password} '
                        f'(сообщите его пользователю)')
                else:
                    messages.error(request, 'Пользователь не найден')
                    
        except Exception as e:
            messages.error(request, f'Ошибка при сбросе пароля: {str(e)}')
            logger.error(f"Error resetting password for user {user_id}: {e}")
    
    return redirect('admin_user_edit', user_id=user_id)


@employee_required
@check_employee_role('ADMIN')
def admin_employees_list(request):
    """Список сотрудников"""
    from django.db import connection

    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', 'all')

    query = """
        SELECT 
            e.id::text, e.full_name, e.email, 
            e.is_active, e.created_at, e.updated_at,
            STRING_AGG(DISTINCT r.code, ', ') as roles
        FROM cinema.employees e
        LEFT JOIN cinema.employee_roles er ON er.employee_id = e.id
        LEFT JOIN cinema.roles r ON r.id = er.role_id
    """
    
    where_clauses = []
    params = []
    
    if search_query:
        where_clauses.append("""
            (e.full_name ILIKE %s OR e.email ILIKE %s 
             OR e.id::text ILIKE %s)
        """)
        params.extend([f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'])
    
    if status_filter and status_filter != 'all':
        if status_filter == 'active':
            where_clauses.append("e.is_active = true")
        elif status_filter == 'inactive':
            where_clauses.append("e.is_active = false")
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    query += """
        GROUP BY e.id, e.full_name, e.email, e.is_active, 
                 e.created_at, e.updated_at
        ORDER BY e.created_at DESC
    """
    
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        employees = []
        for row in cursor.fetchall():
            employees.append(dict(zip(columns, row)))
        
        cursor.execute("SELECT COUNT(*) FROM cinema.employees")
        total_employees = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM cinema.employees WHERE is_active = true")
        active_employees = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM cinema.employees WHERE is_active = false")
        inactive_employees = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT id::text, code, name FROM cinema.roles ORDER BY name")
        all_roles = cursor.fetchall()
        
        stats = (total_employees, active_employees, inactive_employees)
    
    return render(request, 'employees/admin/employees/admin_employees_list.html', {
        'employees': employees,
        'all_roles': all_roles,
        'search_query': search_query,
        'status_filter': status_filter,
        'stats': stats,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_employee_create(request):
    """Создание нового сотрудника"""
    from django.db import connection
    from django.contrib.auth.hashers import make_password
    import uuid
    
    if request.method == 'POST':
        try:
            full_name = request.POST.get('full_name', '').strip()
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '')
            confirm_password = request.POST.get('confirm_password', '')
            is_active = request.POST.get('is_active') == 'on'
            roles = request.POST.getlist('roles', [])
            
            if not full_name or not email:
                messages.error(request, 'ФИО и email обязательны')
                return redirect('admin_employee_create')
            
            if not password:
                messages.error(request, 'Пароль обязателен')
                return redirect('admin_employee_create')
            
            if password != confirm_password:
                messages.error(request, 'Пароли не совпадают')
                return redirect('admin_employee_create')
            
            if len(password) < 6:
                messages.error(request, 'Пароль должен содержать минимум 6 символов')
                return redirect('admin_employee_create')

            password_hash = make_password(password)
            
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM cinema.employees WHERE email = %s", [email])
                if cursor.fetchone():
                    messages.error(request, 'Сотрудник с таким email уже существует')
                    return redirect('admin_employee_create')

                employee_id = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO cinema.employees 
                    (id, full_name, email, password_hash, is_active, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                    RETURNING id
                """, [employee_id, full_name, email, password_hash, is_active])
                
                for role_id in roles:
                    cursor.execute("""
                        INSERT INTO cinema.employee_roles (employee_id, role_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                    """, [employee_id, role_id])
                
                if any(role_id for role_id in roles if role_id in ['ADMIN', 'admin']):
                    cursor.execute("SELECT id FROM cinema.subscription_plans WHERE code = 'ADMIN_ACCESS'")
                    admin_plan = cursor.fetchone()
                    
                    if admin_plan:
                        admin_plan_id = admin_plan[0]
                        cursor.execute("SELECT id FROM cinema.users WHERE email = %s", [email])
                        user = cursor.fetchone()
                        
                        if user:
                            user_id = user[0]
                            cursor.execute("""
                                INSERT INTO cinema.user_subscriptions 
                                (id, user_id, plan_id, status, started_at, expires_at)
                                VALUES (gen_random_uuid(), %s, %s, 'active', NOW(), NULL)
                                ON CONFLICT DO NOTHING
                            """, [user_id, admin_plan_id])
                
                messages.success(request, f'Сотрудник {full_name} ({email}) успешно создан!')
                return redirect('admin_employees_list')
                
        except Exception as e:
            messages.error(request, f'Ошибка при создании сотрудника: {str(e)}')
            logger.error(f"Error creating employee: {e}")

    with connection.cursor() as cursor:
        cursor.execute("SELECT id::text, code, name FROM cinema.roles ORDER BY name")
        all_roles = cursor.fetchall()
    
    return render(request, 'employees/admin/employees/admin_employee_create.html', {
        'all_roles': all_roles,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_employee_edit(request, employee_id):
    """Редактирование сотрудника"""
    from django.db import connection
    from django.contrib.auth.hashers import make_password
    
    if request.method == 'POST':
        try:
            full_name = request.POST.get('full_name', '').strip()
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '').strip()
            is_active = request.POST.get('is_active') == 'on'
            roles = request.POST.getlist('roles', [])
            

            if not full_name or not email:
                messages.error(request, 'ФИО и email обязательны')
                return redirect('admin_employee_edit', employee_id=employee_id)
            
            with connection.cursor() as cursor:

                cursor.execute("""
                    SELECT 1 FROM cinema.employees 
                    WHERE email = %s AND id != %s
                """, [email, employee_id])
                
                if cursor.fetchone():
                    messages.error(request, 'Сотрудник с таким email уже существует')
                    return redirect('admin_employee_edit', employee_id=employee_id)

                if password:

                    password_hash = make_password(password)
                    cursor.execute("""
                        UPDATE cinema.employees 
                        SET full_name = %s, email = %s, password_hash = %s, 
                            is_active = %s, updated_at = NOW()
                        WHERE id = %s
                    """, [full_name, email, password_hash, is_active, employee_id])
                else:

                    cursor.execute("""
                        UPDATE cinema.employees 
                        SET full_name = %s, email = %s, is_active = %s, 
                            updated_at = NOW()
                        WHERE id = %s
                    """, [full_name, email, is_active, employee_id])
                

                cursor.execute("DELETE FROM cinema.employee_roles WHERE employee_id = %s", [employee_id])
                for role_id in roles:
                    cursor.execute("""
                        INSERT INTO cinema.employee_roles (employee_id, role_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                    """, [employee_id, role_id])

                is_admin = any(role_id for role_id in roles if role_id in ['ADMIN', 'admin'])
                

                cursor.execute("SELECT id FROM cinema.subscription_plans WHERE code = 'ADMIN_ACCESS'")
                admin_plan = cursor.fetchone()
                
                if is_admin and admin_plan:
                    admin_plan_id = admin_plan[0]

                    cursor.execute("SELECT id FROM cinema.users WHERE email = %s", [email])
                    user = cursor.fetchone()
                    
                    if user:
                        user_id = user[0]

                        cursor.execute("""
                            INSERT INTO cinema.user_subscriptions 
                            (id, user_id, plan_id, status, started_at, expires_at)
                            VALUES (gen_random_uuid(), %s, %s, 'active', NOW(), NULL)
                            ON CONFLICT DO NOTHING
                        """, [user_id, admin_plan_id])
                
                messages.success(request, f'Сотрудник {full_name} успешно обновлен!')
                return redirect('admin_employees_list')
                
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении сотрудника: {str(e)}')
            logger.error(f"Error updating employee {employee_id}: {e}")
    

    with connection.cursor() as cursor:

        cursor.execute("""
            SELECT 
                id::text, full_name, email, 
                is_active, created_at, updated_at
            FROM cinema.employees 
            WHERE id = %s
        """, [employee_id])
        
        employee = cursor.fetchone()
        if not employee:
            messages.error(request, 'Сотрудник не найден')
            return redirect('admin_employees_list')

        cursor.execute("""
            SELECT r.id::text, r.code, r.name
            FROM cinema.employee_roles er
            JOIN cinema.roles r ON r.id = er.role_id
            WHERE er.employee_id = %s
        """, [employee_id])
        employee_roles = [row[0] for row in cursor.fetchall()]
        

        cursor.execute("SELECT id::text, code, name FROM cinema.roles ORDER BY name")
        all_roles = cursor.fetchall()
    
    return render(request, 'employees/admin/employees/admin_employee_edit.html', {
        'employee': {
            'id': employee[0],
            'full_name': employee[1],
            'email': employee[2],
            'is_active': employee[3],
            'created_at': employee[4],
            'updated_at': employee[5],
        },
        'employee_roles': employee_roles,
        'all_roles': all_roles,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_employee_delete(request, employee_id):
    """Удаление сотрудника"""
    from django.db import connection
    

    current_employee_id = request.session.get('employee_id')
    if current_employee_id == employee_id:
        messages.error(request, 'Вы не можете удалить самого себя')
        return redirect('admin_employees_list')
    
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:

                cursor.execute("SELECT full_name, email FROM cinema.employees WHERE id = %s", [employee_id])
                employee_info = cursor.fetchone()
                
                if employee_info:
                    full_name, email = employee_info
                    

                    cursor.execute("DELETE FROM cinema.employees WHERE id = %s", [employee_id])
                    
                    messages.success(request, f'Сотрудник {full_name} ({email}) удален')
                else:
                    messages.error(request, 'Сотрудник не найден')
                    
        except Exception as e:
            messages.error(request, f'Ошибка при удалении сотрудника: {str(e)}')
            logger.error(f"Error deleting employee {employee_id}: {e}")
    
    return redirect('admin_employees_list')

@employee_required
@check_employee_role('ADMIN')
def admin_employee_toggle_status(request, employee_id):
    """Активация/деактивация сотрудника"""
    from django.db import connection
    

    current_employee_id = request.session.get('employee_id')
    if current_employee_id == employee_id:
        messages.error(request, 'Вы не можете деактивировать самого себя')
        return redirect('admin_employees_list')
    
    if request.method == 'POST':
        try:
            action = request.POST.get('action', 'toggle')
            
            with connection.cursor() as cursor:

                cursor.execute("SELECT full_name, is_active FROM cinema.employees WHERE id = %s", [employee_id])
                employee_info = cursor.fetchone()
                
                if employee_info:
                    full_name, is_active = employee_info
                    
                    if action == 'activate':
                        cursor.execute("""
                            UPDATE cinema.employees 
                            SET is_active = true, updated_at = NOW()
                            WHERE id = %s
                        """, [employee_id])
                        messages.success(request, f'Сотрудник {full_name} активирован')
                    elif action == 'deactivate':
                        cursor.execute("""
                            UPDATE cinema.employees 
                            SET is_active = false, updated_at = NOW()
                            WHERE id = %s
                        """, [employee_id])
                        messages.success(request, f'Сотрудник {full_name} деактивирован')
                    else:

                        new_status = not is_active
                        cursor.execute("""
                            UPDATE cinema.employees 
                            SET is_active = %s, updated_at = NOW()
                            WHERE id = %s
                        """, [new_status, employee_id])
                        
                        status_text = "активирован" if new_status else "деактивирован"
                        messages.success(request, f'Сотрудник {full_name} {status_text}')
                else:
                    messages.error(request, 'Сотрудник не найден')
                    
        except Exception as e:
            messages.error(request, f'Ошибка: {str(e)}')
            logger.error(f"Error toggling employee status {employee_id}: {e}")
    
    return redirect('admin_employees_list')

@employee_required
@check_employee_role('ADMIN')
def admin_employee_reset_password(request, employee_id):
    """Сброс пароля сотрудника"""
    from django.db import connection
    from django.contrib.auth.hashers import make_password
    import secrets
    import string
    
    if request.method == 'POST':
        try:
            alphabet = string.ascii_letters + string.digits
            new_password = ''.join(secrets.choice(alphabet) for _ in range(12))

            password_hash = make_password(new_password)
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE cinema.employees 
                    SET password_hash = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING full_name, email
                """, [password_hash, employee_id])
                
                result = cursor.fetchone()
                if result:
                    full_name, email = result

                    messages.success(request, 
                        f'Пароль сотрудника {full_name} сброшен! Новый пароль: {new_password} '
                        f'(сообщите его сотруднику)')
                else:
                    messages.error(request, 'Сотрудник не найден')
                    
        except Exception as e:
            messages.error(request, f'Ошибка при сбросе пароля: {str(e)}')
            logger.error(f"Error resetting password for employee {employee_id}: {e}")
    
    return redirect('admin_employee_edit', employee_id=employee_id)


@employee_required
@check_employee_role('ADMIN')
def admin_user_activity(request, user_id):
    """Просмотр активности пользователя"""
    from django.db import connection
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                id::text, email, login, avatar_url, 
                is_active, created_at, updated_at
            FROM cinema.users 
            WHERE id = %s
        """, [user_id])
        
        user = cursor.fetchone()
        if not user:
            messages.error(request, 'Пользователь не найден')
            return redirect('admin_users_list')

        cursor.execute("""
            SELECT r.code, r.name
            FROM cinema.user_roles ur
            JOIN cinema.roles r ON r.id = ur.role_id
            WHERE ur.user_id = %s
        """, [user_id])
        user_roles = cursor.fetchall()

        cursor.execute("""
            SELECT 
                c.title, c.type, c.price, pur.purchased_at,
                CASE WHEN c.is_free THEN 'Бесплатно' ELSE 'Платно' END as price_type
            FROM cinema.purchases pur
            JOIN cinema.content c ON c.id = pur.content_id
            WHERE pur.user_id = %s
            ORDER BY pur.purchased_at DESC
            LIMIT 50
        """, [user_id])
        purchases = cursor.fetchall()

        cursor.execute("""
            SELECT 
                sp.name, sp.code, us.status, 
                us.started_at, us.expires_at,
                p.amount, p.status as payment_status
            FROM cinema.user_subscriptions us
            JOIN cinema.subscription_plans sp ON sp.id = us.plan_id
            LEFT JOIN cinema.payments p ON p.subscription_id = us.id
            WHERE us.user_id = %s
            ORDER BY us.started_at DESC
            LIMIT 20
        """, [user_id])
        subscriptions = cursor.fetchall()

        cursor.execute("""
            SELECT 
                c.title, c.type,
                wh.watched_at, wh.progress_sec,
                e.title as episode_title, e.episode_num,
                s.season_num
            FROM cinema.watch_history wh
            JOIN cinema.content c ON c.id = wh.content_id
            LEFT JOIN cinema.episodes e ON e.id = wh.episode_id
            LEFT JOIN cinema.seasons s ON s.id = e.season_id
            WHERE wh.user_id = %s
            ORDER BY wh.watched_at DESC
            LIMIT 30
        """, [user_id])
        watch_history = cursor.fetchall()

        cursor.execute("""
            SELECT 
                c.title, c.type, fav.created_at
            FROM cinema.favorites fav
            JOIN cinema.content c ON c.id = fav.content_id
            WHERE fav.user_id = %s
            ORDER BY fav.created_at DESC
            LIMIT 20
        """, [user_id])
        favorites = cursor.fetchall()

        cursor.execute("""
            SELECT 
                c.title, cr.rating, cr.comment, cr.created_at
            FROM cinema.content_reviews cr
            JOIN cinema.content c ON c.id = cr.content_id
            WHERE cr.user_id = %s
            ORDER BY cr.created_at DESC
            LIMIT 20
        """, [user_id])
        reviews = cursor.fetchall()

        cursor.execute("""
            SELECT 
                pl.title, pl.is_public, pl.created_at,
                COUNT(pli.content_id) as items_count
            FROM cinema.playlists pl
            LEFT JOIN cinema.playlist_items pli ON pli.playlist_id = pl.id
            WHERE pl.user_id = %s
            GROUP BY pl.id, pl.title, pl.is_public, pl.created_at
            ORDER BY pl.created_at DESC
            LIMIT 10
        """, [user_id])
        playlists = cursor.fetchall()

        cursor.execute("""
            SELECT 
                COUNT(DISTINCT pur.id) as purchase_count,
                COUNT(DISTINCT us.id) as subscription_count,
                COUNT(DISTINCT wh.id) as watch_count,
                COUNT(DISTINCT fav.content_id) as favorite_count,
                COUNT(DISTINCT cr.id) as review_count,
                COUNT(DISTINCT pl.id) as playlist_count,
                COALESCE((
                    SELECT SUM(amount) 
                    FROM cinema.payments p 
                    WHERE p.status = 'paid' 
                    AND (
                        p.purchase_id IN (SELECT id FROM cinema.purchases WHERE user_id = u.id) 
                        OR 
                        p.subscription_id IN (SELECT id FROM cinema.user_subscriptions WHERE user_id = u.id)
                    )
                ), 0) as total_spent
            FROM cinema.users u
            LEFT JOIN cinema.purchases pur ON pur.user_id = u.id
            LEFT JOIN cinema.user_subscriptions us ON us.user_id = u.id
            LEFT JOIN cinema.watch_history wh ON wh.user_id = u.id
            LEFT JOIN cinema.favorites fav ON fav.user_id = u.id
            LEFT JOIN cinema.content_reviews cr ON cr.user_id = u.id
            LEFT JOIN cinema.playlists pl ON pl.user_id = u.id
            WHERE u.id = %s
            GROUP BY u.id
        """, [user_id])
        stats = cursor.fetchone() or (0, 0, 0, 0, 0, 0, 0)
    
    return render(request, 'employees/admin/users/admin_user_activity.html', {
        'user': {
            'id': user[0],
            'email': user[1],
            'login': user[2],
            'avatar_url': user[3],
            'is_active': user[4],
            'created_at': user[5],
            'updated_at': user[6],
        },
        'user_roles': user_roles,
        'purchases': purchases,
        'subscriptions': subscriptions,
        'watch_history': watch_history,
        'favorites': favorites,
        'reviews': reviews,
        'playlists': playlists,
        'stats': stats,
        'employee_name': request.session.get('employee_name'),
    })


@employee_required
@check_employee_role('ADMIN')
def admin_user_purchases(request):
    """Управление покупками контента пользователями"""
    from django.db import connection
    import datetime

    search_query = request.GET.get('search', '').strip()
    user_filter = request.GET.get('user_id', '')
    content_filter = request.GET.get('content_id', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    query = """
        SELECT 
            pur.id::text, pur.user_id::text, pur.content_id::text,
            pur.purchased_at,
            u.login as user_login, u.email as user_email,
            c.title as content_title, c.type as content_type,
            c.price as content_price, c.is_free,
            p.amount as payment_amount, p.status as payment_status,
            p.paid_at as payment_date
        FROM cinema.purchases pur
        JOIN cinema.users u ON u.id = pur.user_id
        JOIN cinema.content c ON c.id = pur.content_id
        LEFT JOIN cinema.payments p ON p.purchase_id = pur.id
        WHERE c.price > 0 AND NOT c.is_free  -- Только платный контент
    """
    
    where_clauses = []
    params = []
    
    if search_query:
        where_clauses.append("""
            (u.login ILIKE %s OR u.email ILIKE %s 
             OR c.title ILIKE %s OR pur.id::text ILIKE %s)
        """)
        params.extend([f'%{search_query}%', f'%{search_query}%', 
                      f'%{search_query}%', f'%{search_query}%'])
    
    if user_filter:
        where_clauses.append("pur.user_id = %s")
        params.append(user_filter)
    
    if content_filter:
        where_clauses.append("pur.content_id = %s")
        params.append(content_filter)
    
    if date_from:
        where_clauses.append("DATE(pur.purchased_at) >= %s")
        params.append(date_from)
    
    if date_to:
        where_clauses.append("DATE(pur.purchased_at) <= %s")
        params.append(date_to)
    
    if where_clauses:
        query += " AND " + " AND ".join(where_clauses)
    
    query += " ORDER BY pur.purchased_at DESC"
    
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        purchases = []
        for row in cursor.fetchall():
            purchases.append(dict(zip(columns, row)))

        cursor.execute("""
            SELECT 
                COUNT(*) as total_purchases,
                COALESCE(SUM(c.price), 0) as total_amount,
                COUNT(DISTINCT pur.user_id) as unique_users,
                COUNT(DISTINCT pur.content_id) as unique_content
            FROM cinema.purchases pur
            JOIN cinema.content c ON c.id = pur.content_id
            WHERE c.price > 0 AND NOT c.is_free
        """)
        stats = cursor.fetchone() or (0, 0, 0, 0)
        

        cursor.execute("""
            SELECT DISTINCT 
                u.id::text, u.login, u.email
            FROM cinema.purchases pur
            JOIN cinema.users u ON u.id = pur.user_id
            JOIN cinema.content c ON c.id = pur.content_id
            WHERE c.price > 0 AND NOT c.is_free
            ORDER BY u.login
            LIMIT 50
        """)
        users = cursor.fetchall()

        cursor.execute("""
            SELECT DISTINCT 
                c.id::text, c.title, c.type
            FROM cinema.purchases pur
            JOIN cinema.content c ON c.id = pur.content_id
            WHERE c.price > 0 AND NOT c.is_free
            ORDER BY c.title
            LIMIT 50
        """)
        content_list = cursor.fetchall()
    
    return render(request, 'employees/admin/purchases/admin_user_purchases.html', {
        'purchases': purchases,
        'users': users,
        'content_list': content_list,
        'search_query': search_query,
        'user_filter': user_filter,
        'content_filter': content_filter,
        'date_from': date_from,
        'date_to': date_to,
        'stats': stats,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_grant_purchase(request):
    """Выдача покупки контента пользователю"""
    from django.db import connection
    import datetime
    
    if request.method == 'POST':
        try:
            user_id = request.POST.get('user_id', '').strip()
            content_id = request.POST.get('content_id')
            purchase_date = request.POST.get('purchase_date', '')
            
            if not user_id or not content_id:
                messages.error(request, 'Укажите пользователя и контент')
                return redirect('admin_grant_purchase')

            purchased_at = None
            if purchase_date:

                if 'T' in purchase_date:
                    purchased_at = datetime.datetime.fromisoformat(purchase_date)
                else:
                    purchased_at = datetime.datetime.strptime(purchase_date, '%Y-%m-%d %H:%M:%S')
            
            with connection.cursor() as cursor:
                cursor.execute("SELECT login FROM cinema.users WHERE id = %s", [user_id])
                user_info = cursor.fetchone()
                if not user_info:
                    messages.error(request, 'Пользователь не найден')
                    return redirect('admin_grant_purchase')
                
                cursor.execute("""
                    SELECT title, price, is_free FROM cinema.content 
                    WHERE id = %s AND price > 0 AND NOT is_free
                """, [content_id])
                content_info = cursor.fetchone()
                if not content_info:
                    messages.error(request, 'Контент не найден или он бесплатный')
                    return redirect('admin_grant_purchase')
                
                content_title, content_price, is_free = content_info
                user_login = user_info[0]

                cursor.execute("""
                    SELECT id FROM cinema.purchases 
                    WHERE user_id = %s AND content_id = %s
                """, [user_id, content_id])
                
                if cursor.fetchone():
                    messages.warning(request, 
                        f'У пользователя {user_login} уже есть покупка контента "{content_title}"')
                    return redirect('admin_user_purchases')

                if purchased_at:
                    cursor.execute("""
                        INSERT INTO cinema.purchases 
                        (id, user_id, content_id, purchased_at)
                        VALUES (gen_random_uuid(), %s, %s, %s)
                        RETURNING id::text
                    """, [user_id, content_id, purchased_at])
                else:
                    cursor.execute("""
                        INSERT INTO cinema.purchases 
                        (id, user_id, content_id)
                        VALUES (gen_random_uuid(), %s, %s, DEFAULT)
                        RETURNING id::text
                    """, [user_id, content_id])
                
                purchase_id = cursor.fetchone()[0]

                create_payment = request.POST.get('create_payment', 'off') == 'on'
                if create_payment and content_price > 0:
                    import uuid
                    txn_uuid = str(uuid.uuid4())
                    cursor.execute("""
                        INSERT INTO cinema.payments 
                        (id, txn_uuid, purchase_id, amount, status, paid_at)
                        VALUES (
                            gen_random_uuid(),
                            %s,
                            %s,
                            %s,
                            'paid',
                            %s
                        )
                    """, [
                        txn_uuid,
                        purchase_id,
                        content_price,
                        purchased_at or datetime.datetime.now()
                    ])
                
                messages.success(request, 
                    f'Покупка контента "{content_title}" успешно выдана пользователю {user_login}')
                return redirect('admin_user_purchases')
                
        except Exception as e:
            messages.error(request, f'Ошибка при выдаче покупки: {str(e)}')
            logger.error(f"Error granting purchase: {e}")

    with connection.cursor() as cursor:

        cursor.execute("""
            SELECT id::text, login, email 
            FROM cinema.users 
            WHERE is_active = true
            ORDER BY login
            LIMIT 100
        """)
        users = cursor.fetchall()

        cursor.execute("""
            SELECT id::text, title, type, price::text, release_year
            FROM cinema.content 
            WHERE price > 0 AND NOT is_free
            ORDER BY title
            LIMIT 100
        """)
        content_list = cursor.fetchall()

    now = datetime.datetime.now()
    now_formatted = now.strftime('%Y-%m-%dT%H:%M')
    
    return render(request, 'employees/admin/purchases/admin_grant_purchase.html', {
        'users': users,
        'content_list': content_list,
        'now': now_formatted,
        'employee_name': request.session.get('employee_name'),
    })

@employee_required
@check_employee_role('ADMIN')
def admin_purchase_delete(request, purchase_id):
    """Удаление покупки контента"""
    from django.db import connection
    
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT u.login, c.title
                    FROM cinema.purchases pur
                    JOIN cinema.users u ON u.id = pur.user_id
                    JOIN cinema.content c ON c.id = pur.content_id
                    WHERE pur.id = %s
                """, [purchase_id])
                
                result = cursor.fetchone()
                if result:
                    user_login, content_title = result
                    
    
                    cursor.execute("DELETE FROM cinema.payments WHERE purchase_id = %s", [purchase_id])
                    
     
                    cursor.execute("DELETE FROM cinema.purchases WHERE id = %s", [purchase_id])
                    
                    messages.success(request, 
                        f'Покупка контента "{content_title}" пользователя {user_login} удалена')
                else:
                    messages.error(request, 'Покупка не найдена')
        except Exception as e:
            messages.error(request, f'Ошибка при удалении покупки: {str(e)}')
            logger.error(f"Error deleting purchase {purchase_id}: {e}")
    
    return redirect('admin_user_purchases')

@employee_required
@check_employee_role('ADMIN')
def admin_purchase_refund(request, purchase_id):
    """Возврат средств за покупку контента"""
    from django.db import connection
    import datetime
    
    if request.method == 'POST':
        try:
            refund_reason = request.POST.get('refund_reason', '').strip()
            
            with connection.cursor() as cursor:

                cursor.execute("""
                    SELECT 
                        u.login, c.title, c.price,
                        p.id as payment_id, p.amount, p.status
                    FROM cinema.purchases pur
                    JOIN cinema.users u ON u.id = pur.user_id
                    JOIN cinema.content c ON c.id = pur.content_id
                    LEFT JOIN cinema.payments p ON p.purchase_id = pur.id
                    WHERE pur.id = %s
                """, [purchase_id])
                
                result = cursor.fetchone()
                if result:
                    user_login, content_title, content_price, payment_id, payment_amount, payment_status = result
                    
                    if payment_id and payment_status == 'paid':

                        cursor.execute("""
                            INSERT INTO cinema.payments 
                            (id, txn_uuid, purchase_id, amount, status, 
                             description, paid_at, created_at)
                            VALUES (
                                gen_random_uuid(),
                                %s,
                                %s,
                                %s,
                                'refunded',
                                %s,
                                NOW(),
                                NOW()
                            )
                        """, [
                            f"REFUND_{payment_id[:8]}",
                            purchase_id,
                            f"-{payment_amount}",
                            f"Возврат средств. Причина: {refund_reason}"
                        ])
                        
                        messages.success(request, 
                            f'Возврат средств за контент "{content_title}" '
                            f'пользователю {user_login} оформлен')
                    else:

                        cursor.execute("DELETE FROM cinema.purchases WHERE id = %s", [purchase_id])
                        messages.success(request, 
                            f'Покупка контента "{content_title}" пользователя {user_login} отменена')
                else:
                    messages.error(request, 'Покупка не найдена')
        except Exception as e:
            messages.error(request, f'Ошибка при возврате средств: {str(e)}')
            logger.error(f"Error refunding purchase {purchase_id}: {e}")
    
    return redirect('admin_user_purchases')

@employee_required
@check_employee_role('ADMIN')
def export_purchases(request):
    """Экспорт покупок в CSV"""
    from django.db import connection
    import io
    import csv
    import datetime
    from django.http import HttpResponse
    
    with connection.cursor() as cursor:
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        

        writer.writerow(['Отчет по покупкам контента', f'Сгенерирован: {datetime.datetime.now().strftime("%d.%m.%Y %H:%M")}'])
        writer.writerow([])
        

        cursor.execute("""
            SELECT 
                pur.id::text, u.login, u.email, c.title, c.type, c.price::text,
                pur.purchased_at, p.status as payment_status, p.amount::text,
                CASE WHEN c.is_free THEN 'Бесплатно' ELSE 'Платно' END as price_type
            FROM cinema.purchases pur
            JOIN cinema.users u ON u.id = pur.user_id
            JOIN cinema.content c ON c.id = pur.content_id
            LEFT JOIN cinema.payments p ON p.purchase_id = pur.id
            WHERE c.price > 0 AND NOT c.is_free
            ORDER BY pur.purchased_at DESC
        """)
        
        purchases = cursor.fetchall()

        writer.writerow(['ID покупки', 'Пользователь', 'Email', 'Контент', 'Тип', 'Цена', 
                        'Дата покупки', 'Статус оплаты', 'Сумма оплаты', 'Тип цены'])

        for purchase in purchases:
            writer.writerow(purchase)
        
        output.seek(0)
        
        filename = f'purchases_export_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response = HttpResponse(
            output.getvalue(),
            content_type='text/csv; charset=utf-8-sig'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response