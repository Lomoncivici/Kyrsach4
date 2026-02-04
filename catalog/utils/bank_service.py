import requests
import json
from django.conf import settings

class BankService:
    """Клиент для взаимодействия с банковским микросервисом"""

    BASE_URL = "http://localhost:5000/api"
    
    @staticmethod
    def health_check():
        """Проверка доступности банковского сервиса"""
        try:
            response = requests.get("http://localhost:5000/health", timeout=3)
            return response.status_code == 200
        except:
            return False
    
    @staticmethod
    def check_card(card_data):
        """
        Проверка карты
        
        Args:
            card_data: {
                'card_number': '4242424242424242',
                'expiry_month': 12,
                'expiry_year': 25,  # Можно в формате 25 или 2025
                'cvc': '123'
            }
        
        Returns:
            {
                'success': True/False,
                'error': 'Сообщение об ошибке',
                'hint': 'Подсказка', 
                'card': {...}  # При успехе
            }
        """
        try:
            response = requests.post(
                f"{BankService.BASE_URL}/check",
                json=card_data,
                timeout=5
            )
            return response.json()
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': 'Банковский сервис недоступен'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка проверки: {str(e)}'
            }
    
    @staticmethod
    def process_payment(payment_data):
        """
        Обработка платежа
        
        Args:
            payment_data: {
                'card_number': '4242424242424242',
                'expiry_month': 12,
                'expiry_year': 25,
                'cvc': '123',
                'amount': 1000.0
            }
        
        Returns:
            {
                'success': True/False,
                'error': 'Сообщение об ошибке',
                'message': 'Сообщение об успехе',
                'transaction_id': 'TXN12345678',
                'auth_code': '123456'
            }
        """
        try:
            response = requests.post(
                f"{BankService.BASE_URL}/pay",
                json=payment_data,
                timeout=10
            )
            result = response.json()

            print(f"[BankService] Payment result: {result}")
            
            return result
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': 'Банковский сервис недоступен'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка оплаты: {str(e)}'
            }
    
    @staticmethod
    def reset_balances():
        """Сбросить балансы тестовых карт"""
        try:
            response = requests.post(f"{BankService.BASE_URL}/reset", timeout=5)
            return response.json()
        except:
            return {'success': False}
    
    @staticmethod
    def get_test_cards():
        """Получить список тестовых карт"""
        try:
            response = requests.get(f"{BankService.BASE_URL}/cards", timeout=3)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return {
            'success': False,
            'cards': []
        }