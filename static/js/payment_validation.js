document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('payment-form');
  const card = document.getElementById('card_number');
  const exp = document.getElementById('expiry_date');
  const cvc = document.getElementById('cvc');
  const holder = document.getElementById('cardholder_name');

  if (!form || !card || !exp || !cvc || !holder) return;

  function luhn(num) {
    let sum = 0, alt = false;
    for (let i = num.length - 1; i >= 0; i--) {
      let n = +num[i];
      if (alt) {
        n *= 2;
        if (n > 9) n -= 9;
      }
      sum += n;
      alt = !alt;
    }
    return sum % 10 === 0;
  }

  function errorEl() {
    let el = document.getElementById('card-error');
    if (!el) {
      el = document.createElement('div');
      el.id = 'card-error';
      el.className = 'error-message';
      card.closest('.form-section').appendChild(el);
    }
    return el;
  }

  function showFieldError(inputElement, message, errorId = null) {
    let errorElement;
    if (errorId) {
      errorElement = document.getElementById(errorId);
    } else {
      const container = inputElement.closest('.form-section');
      if (container) {
        errorElement = container.querySelector('.field-error');
      }
    }
    
    if (!errorElement) {
      errorElement = document.createElement('div');
      errorElement.className = 'error-message field-error';
      if (errorId) {
        errorElement.id = errorId;
      }
      
      const inputContainer = inputElement.closest('.input-with-icon') || inputElement.parentElement;
      if (inputContainer) {
        inputContainer.parentNode.insertBefore(errorElement, inputContainer.nextSibling);
      } else {
        inputElement.parentElement.appendChild(errorElement);
      }
    }
    
    errorElement.textContent = message;
    errorElement.style.display = 'block';
    inputElement.classList.add('is-invalid');
    
    return errorElement;
  }

  function hideFieldError(inputElement, errorId = null) {
    let errorElement;
    if (errorId) {
      errorElement = document.getElementById(errorId);
    } else {
      const container = inputElement.closest('.form-section');
      if (container) {
        errorElement = container.querySelector('.field-error');
      }
    }
    
    if (errorElement) {
      errorElement.style.display = 'none';
    }
    inputElement.classList.remove('is-invalid');
  }

  function validateCard() {
    const clean = card.value.replace(/\s/g, '');
    const error = errorEl();

    card.classList.remove('is-valid', 'is-invalid');
    error.style.display = 'none';

    if (clean.length < 16) return false;

    if (!luhn(clean)) {
      error.textContent = 'Неверный номер карты';
      error.style.display = 'block';
      card.classList.add('is-invalid');
      return false;
    }

    card.classList.add('is-valid');
    return true;
  }

  card.addEventListener('input', () => {
    const digits = card.value.replace(/\D/g, '').slice(0, 16);

    card.value = digits.replace(/(\d{4})(?=\d)/g, '$1 ');

    validateCard();
  });

  cvc.addEventListener('keydown', e => {
    if (
      !/[0-9]/.test(e.key) &&
      !['Backspace', 'Delete', 'ArrowLeft', 'ArrowRight', 'Tab'].includes(e.key)
    ) {
      e.preventDefault();
    }
  });

  cvc.addEventListener('input', () => {
    cvc.value = cvc.value.replace(/\D/g, '').slice(0, 3);
  });

  holder.addEventListener('input', () => {
    holder.value = holder.value
      .toUpperCase()
      .replace(/[^A-ZА-ЯЁ\s\-]/g, '');
  });

  exp.addEventListener('keydown', e => {
    if (
      !/[0-9]/.test(e.key) &&
      !['Backspace', 'Delete', 'ArrowLeft', 'ArrowRight', 'Tab'].includes(e.key)
    ) {
      e.preventDefault();
    }
  });

  exp.addEventListener('input', () => {
    let digits = exp.value.replace(/\D/g, '').slice(0, 4);

    if (digits.length >= 3) {
      exp.value = digits.slice(0, 2) + '/' + digits.slice(2);
    } else {
      exp.value = digits;
    }

    if (digits.length >= 2) {
      const m = +digits.slice(0, 2);
      const isValidMonth = m >= 1 && m <= 12;
      
      exp.classList.toggle('is-invalid', !isValidMonth);
      
      if (!isValidMonth) {
        showFieldError(exp, 'Месяц должен быть от 01 до 12', 'expiry-error');
      } else if (digits.length === 4) {
        const y = +digits.slice(2, 4);
        const currentYear = new Date().getFullYear() % 100;
        const currentMonth = new Date().getMonth() + 1;
        
        if (y < currentYear || (y === currentYear && m < currentMonth)) {
          showFieldError(exp, 'Срок действия карты истёк', 'expiry-error');
          exp.classList.add('is-invalid');
        } else {
          hideFieldError(exp, 'expiry-error');
          exp.classList.remove('is-invalid');
        }
      } else {
        hideFieldError(exp, 'expiry-error');
        exp.classList.remove('is-invalid');
      }
    } else {
      hideFieldError(exp, 'expiry-error');
      exp.classList.remove('is-invalid');
    }
  });

  form.addEventListener('submit', e => {
    e.preventDefault();

    if (!validateCard()) {
      card.focus();
      return;
    }

    const expiryDigits = exp.value.replace(/\D/g, '');
    if (exp.value.length !== 5 || expiryDigits.length !== 4) {
      showFieldError(exp, 'Введите срок действия MM/YY', 'expiry-error');
      exp.focus();
      return;
    }
    
    const month = parseInt(expiryDigits.slice(0, 2));
    if (month < 1 || month > 12) {
      showFieldError(exp, 'Месяц должен быть от 01 до 12', 'expiry-error');
      exp.focus();
      return;
    }
    
    const currentYear = new Date().getFullYear() % 100;
    const currentMonth = new Date().getMonth() + 1;
    const year = parseInt(expiryDigits.slice(2, 4));
    
    if (year < currentYear || (year === currentYear && month < currentMonth)) {
      showFieldError(exp, 'Срок действия карты истёк', 'expiry-error');
      exp.focus();
      return;
    }
    
    hideFieldError(exp, 'expiry-error');

    if (cvc.value.length !== 3) {
      showFieldError(cvc, 'Введите CVC код (3 цифры)', 'cvc-error');
      cvc.focus();
      return;
    }
    
    hideFieldError(cvc, 'cvc-error');

    if (!holder.value.trim()) {
      showFieldError(holder, 'Введите имя владельца карты', 'holder-error');
      holder.focus();
      return;
    }
    
    hideFieldError(holder, 'holder-error');

    const btn = form.querySelector('.btn-pay');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '⏳ Обработка...';
    }

    setTimeout(() => form.submit(), 0);
  });
});