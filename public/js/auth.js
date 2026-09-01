/**
 * Opinio / Reputation Shield - Business Auth Controller
 * Handles business login and session persistence.
 */

document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.getElementById('loginForm');
  if (loginForm) {
    loginForm.addEventListener('submit', handleLogin);
  }
});

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
      alertBox.textContent = data.error || 'Credenciales no autorizadas o incorrectas.';
    }
  } catch (err) {
    alertBox.style.display = 'block';
    alertBox.style.background = 'rgba(239, 68, 68, 0.15)';
    alertBox.style.color = '#ef4444';
    alertBox.textContent = 'Error de conexión con el servidor.';
  } finally {
    btnSubmit.disabled = false;
    btnSubmit.textContent = 'Ingresar al Panel';
  }
}

function fillDemo(email, password) {
  document.getElementById('loginEmail').value = email;
  document.getElementById('loginPassword').value = password;
  const alertBox = document.getElementById('authAlert');
  if (alertBox) alertBox.style.display = 'none';
}
