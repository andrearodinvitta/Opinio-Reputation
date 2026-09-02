/**
 * Opinio / Reputation Shield - Business Auth Controller
 * Handles business login, direct registration, and session persistence.
 */

document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.getElementById('loginForm');
  if (loginForm) {
    loginForm.addEventListener('submit', handleLogin);
  }

  const registerForm = document.getElementById('registerForm');
  if (registerForm) {
    registerForm.addEventListener('submit', handleRegister);
  }

  // Check URL parameters for tab selection (e.g. /login?tab=register)
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('tab') === 'register' || urlParams.get('action') === 'register') {
    switchAuthTab('register');
  }
});

function switchAuthTab(tab) {
  const tabLoginBtn = document.getElementById('tabLoginBtn');
  const tabRegisterBtn = document.getElementById('tabRegisterBtn');
  const loginForm = document.getElementById('loginForm');
  const registerForm = document.getElementById('registerForm');
  const demoAccountsContainer = document.getElementById('demoAccountsContainer');
  const alertBox = document.getElementById('authAlert');

  if (alertBox) alertBox.style.display = 'none';

  if (tab === 'register') {
    tabRegisterBtn.classList.add('active');
    tabLoginBtn.classList.remove('active');
    loginForm.style.display = 'none';
    registerForm.style.display = 'block';
    if (demoAccountsContainer) demoAccountsContainer.style.display = 'none';
  } else {
    tabLoginBtn.classList.add('active');
    tabRegisterBtn.classList.remove('active');
    loginForm.style.display = 'block';
    registerForm.style.display = 'none';
    if (demoAccountsContainer) demoAccountsContainer.style.display = 'block';
  }
}

async function handleLogin(e) {
  e.preventDefault();
  const email = document.getElementById('loginEmail').value.trim();
  const password = document.getElementById('loginPassword').value;
  const alertBox = document.getElementById('authAlert');
  const btnSubmit = document.getElementById('btnLoginSubmit');

  alertBox.style.display = 'none';
  btnSubmit.disabled = true;
  btnSubmit.textContent = 'Verificando acceso...';

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      if (data.token) {
        localStorage.setItem('session_token', data.token);
      }
      window.location.href = '/dashboard';
    } else {
      alertBox.style.display = 'block';
      alertBox.style.background = 'rgba(239, 68, 68, 0.15)';
      alertBox.style.color = '#ef4444';
      alertBox.style.border = '1px solid rgba(239, 68, 68, 0.3)';
      alertBox.textContent = data.error || 'Credenciales incorrectas o cuenta no encontrada.';
    }
  } catch (err) {
    alertBox.style.display = 'block';
    alertBox.style.background = 'rgba(239, 68, 68, 0.15)';
    alertBox.style.color = '#ef4444';
    alertBox.textContent = 'Error de conexión con el servidor.';
  } finally {
    btnSubmit.disabled = false;
    btnSubmit.textContent = 'Iniciar Sesión en el Panel';
  }
}

async function handleRegister(e) {
  e.preventDefault();
  const business_name = document.getElementById('regBusinessName').value.trim();
  const applicant_name = document.getElementById('regApplicantName').value.trim();
  const email = document.getElementById('regEmail').value.trim().toLowerCase();
  const password = document.getElementById('regPassword').value;
  const phone = document.getElementById('regPhone').value.trim();
  const category = document.getElementById('regCategory').value;
  const alertBox = document.getElementById('authAlert');
  const btnSubmit = document.getElementById('btnRegisterSubmit');

  alertBox.style.display = 'none';
  btnSubmit.disabled = true;
  btnSubmit.textContent = 'Creando tu cuenta y embudo...';

  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        business_name,
        applicant_name,
        email,
        password,
        phone,
        category
      })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      if (data.token) {
        localStorage.setItem('session_token', data.token);
      }
      alertBox.style.display = 'block';
      alertBox.style.background = 'rgba(16, 185, 129, 0.15)';
      alertBox.style.color = '#10b981';
      alertBox.style.border = '1px solid rgba(16, 185, 129, 0.3)';
      alertBox.textContent = '¡Cuenta creada con éxito! Redirigiendo a tu panel...';

      setTimeout(() => {
        window.location.href = data.redirect || '/dashboard';
      }, 500);
    } else {
      alertBox.style.display = 'block';
      alertBox.style.background = 'rgba(239, 68, 68, 0.15)';
      alertBox.style.color = '#ef4444';
      alertBox.style.border = '1px solid rgba(239, 68, 68, 0.3)';
      alertBox.textContent = data.error || 'Error al crear la cuenta.';
      btnSubmit.disabled = false;
      btnSubmit.textContent = '✨ Crear Cuenta y Entrar al Panel';
    }
  } catch (err) {
    alertBox.style.display = 'block';
    alertBox.style.background = 'rgba(239, 68, 68, 0.15)';
    alertBox.style.color = '#ef4444';
    alertBox.textContent = 'Error de conexión con el servidor.';
    btnSubmit.disabled = false;
    btnSubmit.textContent = '✨ Crear Cuenta y Entrar al Panel';
  }
}

function fillDemo(email, password) {
  document.getElementById('loginEmail').value = email;
  document.getElementById('loginPassword').value = password;
  const alertBox = document.getElementById('authAlert');
  if (alertBox) alertBox.style.display = 'none';
}
