from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
import logging

logger = logging.getLogger(__name__)

def send_purchase_confirmation(cinema_user, content, purchase):
    """
    Отправляет email подтверждения покупки контента
    cinema_user - объект CinemaUser из базы
    """
    try:

        user_email = cinema_user.email
        
        if not user_email:
            logger.warning(f"У пользователя {cinema_user.login} нет email в базе")
            return False
        
        subject = f'Подтверждение покупки: {content.title}'

        html_content = render_to_string('emails/purchase_confirmation.html', {
            'user': cinema_user,
            'content': content,
            'purchase': purchase,
        })
        

        text_content = strip_tags(html_content)

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user_email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        logger.info(f"Email о покупке отправлен пользователю {cinema_user.login} ({user_email}) для контента {content.title}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка отправки email о покупке: {e}")
        return False

def send_subscription_confirmation(cinema_user, subscription, plan):
    """
    Отправляет email подтверждения подписки
    cinema_user - объект CinemaUser из базы
    """
    try:

        user_email = cinema_user.email
        
        if not user_email:
            logger.warning(f"У пользователя {cinema_user.login} нет email в базе")
            return False
        
        subject = f'Подписка {plan.name} активирована'
        

        html_content = render_to_string('emails/subscription_confirmation.html', {
            'user': cinema_user,
            'subscription': subscription,
            'plan': plan,
        })
        

        text_content = strip_tags(html_content)
        

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user_email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        logger.info(f"Email о подписке отправлен пользователю {cinema_user.login} ({user_email}) для плана {plan.name}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка отправки email о подписке: {e}")
        return False

def send_payment_receipt(cinema_user, payment, purchase=None, subscription=None):
    """
    Отправляет email с чеком об оплате
    cinema_user - объект CinemaUser из базы
    """
    try:

        user_email = cinema_user.email
        
        if not user_email:
            logger.warning(f"У пользователя {cinema_user.login} нет email в базе")
            return False
        
        if purchase:
            subject = f'Чек об оплате покупки #{str(payment.id)[:8]}'
        elif subscription:
            subject = f'Чек об оплате подписки #{str(payment.id)[:8]}'
        else:
            subject = 'Чек об оплате'
        
        html_content = render_to_string('emails/payment_receipt.html', {
            'user': cinema_user,
            'payment': payment,
            'purchase': purchase,
            'subscription': subscription,
        })
        
        text_content = strip_tags(html_content)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user_email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        logger.info(f"Чек об оплате отправлен пользователю {cinema_user.login} ({user_email})")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка отправки чека: {e}")
        return False

def send_combined_email(cinema_user, payment, purchase=None, subscription=None):
    """
    Отправляет сразу и подтверждение, и чек
    """
    try:
        user_email = cinema_user.email
        
        if not user_email:
            logger.warning(f"У пользователя {cinema_user.login} нет email в базе")
            return False
        
        if purchase:

            subject = f'Подтверждение покупки и чек - {purchase.content.title}'
            

            confirmation_html = render_to_string('emails/purchase_confirmation.html', {
                'user': cinema_user,
                'content': purchase.content,
                'purchase': purchase,
            })
            
            receipt_html = render_to_string('emails/payment_receipt.html', {
                'user': cinema_user,
                'payment': payment,
                'purchase': purchase,
                'subscription': None,
            })
            

            combined_html = f"""
            {confirmation_html}
            <hr style="margin: 40px 0; border: 1px solid #ddd;">
            <h2 style="text-align: center; margin-bottom: 20px;">📋 Чек об оплате</h2>
            {receipt_html}
            """
            
        elif subscription:

            subject = f'Подтверждение подписки и чек - {subscription.plan.name}'
            
            confirmation_html = render_to_string('emails/subscription_confirmation.html', {
                'user': cinema_user,
                'subscription': subscription,
                'plan': subscription.plan,
            })
            
            receipt_html = render_to_string('emails/payment_receipt.html', {
                'user': cinema_user,
                'payment': payment,
                'purchase': None,
                'subscription': subscription,
            })
            
 
            combined_html = f"""
            {confirmation_html}
            <hr style="margin: 40px 0; border: 1px solid #ddd;">
            <h2 style="text-align: center; margin-bottom: 20px;">📋 Чек об оплате</h2>
            {receipt_html}
            """
        
        else:
            return False
        
        text_content = strip_tags(combined_html)
        

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email='КИНОВЕЧЕР <kinovecheronline@gmail.com>',
            to=[user_email],
        )
        email.attach_alternative(combined_html, "text/html")
        email.send()
        
        logger.info(f"Объединенное письмо отправлено пользователю {cinema_user.login} ({user_email})")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка отправки объединенного письма: {e}")
        return False