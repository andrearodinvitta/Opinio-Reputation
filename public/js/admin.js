/**
 * Opinio / Reputation Shield - Superadmin Dashboard Controller
 * Handles access requests approval, business moderation, status toggling, and global metrics.
 */

let currentAdmin = null;
let currentRequests = [];
let currentBusinesses = [];
let activeRequestFilter = 'pending';

function getAdminAuthHeader() {
  const token = localStorage.getItem('admin_token');
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

async function adminFetch(url, options = {}) {
  options.headers = {
    ...getAdminAuthHeader(),
    ...(options.headers || {})
  };
  return fetch(url, options);
}

document.addEventListener('DOMContentLoaded', () => {
  initAdminTabs();
  checkAdminAuth();
  bindAdminEvents();
});

// ---------------------------------------------------------------------------
// Auth & Initialization
// ---------------------------------------------------------------------------

async function checkAdminAuth() {
  try {
    const res = await adminFetch('/api/admin/me');
    if (res.ok) {
      const data = await res.json();
      if (data.success && data.admin) {
        currentAdmin = data.admin;
        showDashboard();
        return;
      }
    }
  } catch (e) {
    console.error('Error verifying admin auth:', e);
  }
  showLogin();
}

function showLogin() {
  document.getElementById('adminLoginSection').style.display = 'flex';
  document.getElementById('adminDashboardSection').style.display = 'none';
}

function showDashboard() {
  document.getElementById('adminLoginSection').style.display = 'none';
  document.getElementById('adminDashboardSection').style.display = 'block';
  loadAdminStats();
  loadAdminRequests(activeRequestFilter);
  loadAdminBusinesses();
}

function bindAdminEvents() {
  // Login form submit
  const loginForm = document.getElementById('adminLoginForm');
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('adminEmail').value.trim();
      const password = document.getElementById('adminPassword').value;
      const alertBox = document.getElementById('adminLoginAlert');
      const submitBtn = document.getElementById('btnAdminLoginSubmit');

      alertBox.style.display = 'none';
      submitBtn.disabled = true;
      submitBtn.textContent = 'Verificando...';

      try {
        const res = await fetch('/api/admin/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        });
        const data = await res.json();

        if (res.ok && data.success) {
          if (data.token) {
            localStorage.setItem('admin_token', data.token);
          }
          currentAdmin = data.admin;
          showDashboard();
        } else {
          alertBox.style.display = 'block';
          alertBox.style.background = 'rgba(239, 68, 68, 0.15)';
          alertBox.style.color = '#ef4444';
          alertBox.style.border = '1px solid rgba(239, 68, 68, 0.3)';
          alertBox.textContent = data.error || 'Credenciales incorrectas.';
        }
      } catch (err) {
        alertBox.style.display = 'block';
        alertBox.textContent = 'Error de conexión con el servidor.';
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Ingresar al Panel Maestro';
      }
    });
  }

  // Logout
  const logoutBtn = document.getElementById('btnAdminLogout');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', async () => {
      await adminFetch('/api/admin/logout', { method: 'POST' });
      localStorage.removeItem('admin_token');
      currentAdmin = null;
      showLogin();
    });
  }

  // Approve Form Submit
  const approveForm = document.getElementById('approveForm');
  if (approveForm) {
    approveForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const reqId = document.getElementById('approveRequestId').value;
      const initialPassword = document.getElementById('initialPassword').value.trim();
      const btn = document.getElementById('btnConfirmApprove');

      btn.disabled = true;
      btn.textContent = 'Aprobando y creando cuenta...';

      try {
        const res = await adminFetch(`/api/admin/requests/${reqId}/approve`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ initial_password: initialPassword })
        });
        const data = await res.json();

        if (res.ok && data.success) {
          const creds = data.credentials;
          document.getElementById('approveModalContent').style.display = 'none';
          document.getElementById('credentialsSuccessView').style.display = 'block';

          const credsBox = document.getElementById('credentialsDetails');
          credsBox.innerHTML = `
Negocio: ${creds.business_name}
Email de acceso: ${creds.email}
Contraseña temporal: ${creds.temporary_password}
Panel de administración: ${window.location.origin}/login
Enlace público para clientes: ${window.location.origin}/r/${creds.slug}
          `.trim();

          document.getElementById('btnCopyCredentials').onclick = () => {
            navigator.clipboard.writeText(credsBox.innerText);
            alert('¡Credenciales copiadas al portapapeles!');
          };

          loadAdminStats();
        } else {
          alert(data.error || 'Error al aprobar solicitud.');
        }
      } catch (err) {
        alert('Error de conexión.');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Aprobar y Crear Cuenta';
      }
    });
  }

  // Reject Form Submit
  const rejectForm = document.getElementById('rejectForm');
  if (rejectForm) {
    rejectForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const reqId = document.getElementById('rejectRequestId').value;
      const reason = document.getElementById('rejectReason').value.trim();

      try {
        const res = await adminFetch(`/api/admin/requests/${reqId}/reject`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason })
        });
        const data = await res.json();

        if (res.ok && data.success) {
          closeRejectModal();
          loadAdminRequests(activeRequestFilter);
          loadAdminStats();
        } else {
          alert(data.error || 'Error al rechazar solicitud.');
        }
      } catch (err) {
        alert('Error de conexión.');
      }
    });
  }

  // Search businesses
  const searchInput = document.getElementById('businessSearchInput');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      renderBusinesses(searchInput.value.toLowerCase());
    });
  }

  // Reset Password Form
  const resetForm = document.getElementById('resetPasswordForm');
  if (resetForm) {
    resetForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const bId = document.getElementById('resetBusinessId').value;
      const customPw = document.getElementById('newCustomPassword').value.trim();
      const btn = document.getElementById('btnSubmitResetPw');

      btn.disabled = true;
      try {
        const res = await adminFetch(`/api/admin/businesses/${bId}/reset-password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ new_password: customPw })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          document.getElementById('resetPasswordResult').style.display = 'block';
          document.getElementById('resetPasswordResultBox').textContent = `Nueva contraseña establecida: ${data.temporary_password}`;
        } else {
          alert(data.error || 'Error al restablecer contraseña.');
        }
      } catch (err) {
        alert('Error de conexión.');
      } finally {
        btn.disabled = false;
      }
    });
  }
}

// ---------------------------------------------------------------------------
// Tabs Switching
// ---------------------------------------------------------------------------

function initAdminTabs() {
  const tabs = document.querySelectorAll('.admin-tab-btn');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');

      document.querySelectorAll('.admin-tab-view').forEach(view => {
        view.style.display = 'none';
      });
      const targetView = document.getElementById(`tab-${target}`);
      if (targetView) targetView.style.display = 'block';

      if (target === 'requests') loadAdminRequests(activeRequestFilter);
      if (target === 'businesses') loadAdminBusinesses();
      if (target === 'analytics') loadAdminStats();
    });
  });
}

// ---------------------------------------------------------------------------
// Data Fetching & Rendering
// ---------------------------------------------------------------------------

async function loadAdminStats() {
  try {
    const res = await adminFetch('/api/admin/stats');
    if (!res.ok) return;
    const data = await res.json();
    if (data.success && data.stats) {
      const s = data.stats;
      document.getElementById('kpiPendingRequests').textContent = s.pending_requests;
      document.getElementById('kpiActiveBusinesses').textContent = `${s.active_businesses} / ${s.total_businesses}`;
      document.getElementById('kpiTotalGlobalReviews').textContent = s.total_reviews;
      document.getElementById('kpiGlobalSatisfaction').textContent = `${s.satisfaction_rate}%`;

      const badge = document.getElementById('badgePendingCount');
      if (s.pending_requests > 0) {
        badge.style.display = 'inline-block';
        badge.textContent = s.pending_requests;
      } else {
        badge.style.display = 'none';
      }

      // Render audit logs
      if (data.recent_emails) {
        renderAuditLogs(data.recent_emails);
      }
    }
  } catch (e) {
    console.error('Error loading stats:', e);
  }
}

async function loadAdminRequests(status = 'pending') {
  activeRequestFilter = status;
  // Update filter pills UI
  document.querySelectorAll('.filter-pill-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.filter === status);
  });

  const tbody = document.getElementById('requestsTableBody');
  tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">Cargando...</td></tr>`;

  try {
    const res = await adminFetch(`/api/admin/requests?status=${status}`);
    if (!res.ok) throw new Error('Failed to fetch requests');
    const data = await res.json();
    currentRequests = data.requests || [];
    renderRequests(currentRequests);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--danger); padding: 2rem;">Error al cargar solicitudes.</td></tr>`;
  }
}

function renderRequests(requests) {
  const tbody = document.getElementById('requestsTableBody');
  if (!requests || requests.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; padding: 3rem; color: var(--text-muted);">
          No hay solicitudes en este estado.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = requests.map(req => {
    const dateFormatted = req.created_at ? new Date(req.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '--';
    const cleanPhone = req.phone ? req.phone.replace(/[^0-9+]/g, '') : '';
    const whatsappLink = cleanPhone ? `https://wa.me/${cleanPhone.replace('+', '')}?text=Hola%20${encodeURIComponent(req.applicant_name)}%2C%20nos%20contactamos%20desde%20Opinio%20sobre%20tu%20solicitud%20para%20${encodeURIComponent(req.business_name)}` : '#';

    let statusBadge = `<span class="status-chip ${req.status}">${req.status}</span>`;
    let actionButtons = '';

    if (req.status === 'pending') {
      actionButtons = `
        <div style="display: flex; gap: 0.4rem;">
          <button type="button" class="action-btn-sm" style="background: rgba(16,185,129,0.15); color: #10b981; border-color: rgba(16,185,129,0.3);" onclick="openApproveModal(${req.id}, '${escapeHtml(req.business_name)}')">
            ✓ Aprobar
          </button>
          <button type="button" class="action-btn-sm" style="color: var(--danger); border-color: rgba(239,68,68,0.3);" onclick="openRejectModal(${req.id}, '${escapeHtml(req.business_name)}')">
            ✕ Rechazar
          </button>
        </div>
      `;
    } else if (req.status === 'approved') {
      actionButtons = `<span style="font-size: 0.8rem; color: var(--success); font-weight: 600;">✓ Aprobada</span>`;
    } else {
      actionButtons = `<span style="font-size: 0.8rem; color: var(--danger); font-weight: 600;" title="${escapeHtml(req.rejection_reason || '')}">⛔ Rechazada</span>`;
    }

    return `
      <tr>
        <td style="font-size: 0.8rem; color: var(--text-secondary); white-space: nowrap;">${dateFormatted}</td>
        <td>
          <div style="font-weight: 700; color: var(--text-primary);">${escapeHtml(req.applicant_name)}</div>
          <div style="font-size: 0.78rem; color: var(--text-muted);">${escapeHtml(req.email)}</div>
        </td>
        <td>
          <div style="font-weight: 600; color: #38bdf8;">${escapeHtml(req.business_name)}</div>
          <span style="font-size: 0.75rem; background: var(--bg-surface-elevated); padding: 0.15rem 0.45rem; border-radius: 4px; color: var(--text-secondary);">${escapeHtml(req.category || 'General')}</span>
        </td>
        <td>
          <div style="display: flex; align-items: center; gap: 0.4rem;">
            <span>${escapeHtml(req.phone)}</span>
            ${cleanPhone ? `<a href="${whatsappLink}" target="_blank" class="action-btn-sm action-btn-whatsapp" title="Abrir WhatsApp" style="padding: 0.2rem 0.4rem; font-size: 0.75rem;">💬</a>` : ''}
          </div>
        </td>
        <td style="font-size: 0.82rem; color: var(--text-secondary);">
          ${escapeHtml(req.city || 'No especificada')}
          ${req.google_maps_url ? `<br><a href="${req.google_maps_url}" target="_blank" style="color: #60a5fa; text-decoration: underline; font-size: 0.75rem;">Ver Ficha Maps</a>` : ''}
        </td>
        <td>${statusBadge}</td>
        <td>${actionButtons}</td>
      </tr>
    `;
  }).join('');
}

async function loadAdminBusinesses() {
  const tbody = document.getElementById('businessesTableBody');
  tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">Cargando...</td></tr>`;

  try {
    const res = await adminFetch('/api/admin/businesses');
    if (!res.ok) throw new Error('Failed to fetch businesses');
    const data = await res.json();
    currentBusinesses = data.businesses || [];
    renderBusinesses('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--danger); padding: 2rem;">Error al cargar negocios.</td></tr>`;
  }
}

function renderBusinesses(filterQuery = '') {
  const tbody = document.getElementById('businessesTableBody');
  const list = currentBusinesses.filter(b => {
    if (!filterQuery) return true;
    return b.name.toLowerCase().includes(filterQuery) ||
           b.email.toLowerCase().includes(filterQuery) ||
           b.slug.toLowerCase().includes(filterQuery);
  });

  if (list.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; padding: 3rem; color: var(--text-muted);">
          No se encontraron negocios.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = list.map(biz => {
    const isSuspended = biz.status === 'suspended';
    const statusChip = `<span class="status-chip ${isSuspended ? 'suspended' : 'active'}">${isSuspended ? 'Suspendido' : 'Activo'}</span>`;

    return `
      <tr>
        <td>
          <div style="font-weight: 700; color: var(--text-primary); font-size: 0.95rem;">${escapeHtml(biz.name)}</div>
          <div style="font-size: 0.78rem; color: var(--text-secondary);">${escapeHtml(biz.category || 'General')} • ${escapeHtml(biz.city || '')}</div>
        </td>
        <td>
          <a href="/r/${biz.slug}" target="_blank" style="color: #38bdf8; text-decoration: underline; font-size: 0.85rem; font-family: monospace;">
            /r/${biz.slug} ↗
          </a>
        </td>
        <td>
          <div style="font-size: 0.85rem;">${escapeHtml(biz.email)}</div>
          <div style="font-size: 0.78rem; color: var(--text-muted);">${escapeHtml(biz.phone || '--')}</div>
        </td>
        <td>
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span style="font-weight: 800; color: #fbbf24;">★ ${biz.avg_rating || '5.0'}</span>
            <span style="font-size: 0.8rem; color: var(--text-secondary);">(${biz.total_reviews || 0} res.)</span>
          </div>
          <div style="font-size: 0.75rem; color: var(--success);">${biz.positive_reviews || 0} a Google / ${biz.negative_reviews || 0} privados</div>
        </td>
        <td>${statusChip}</td>
        <td>
          <div style="display: flex; gap: 0.4rem; flex-wrap: wrap;">
            <button type="button" class="action-btn-sm" style="background: ${isSuspended ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)'}; color: ${isSuspended ? '#10b981' : '#ef4444'}; border-color: ${isSuspended ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'};" onclick="toggleBusinessStatus(${biz.id}, '${isSuspended ? 'reactivar' : 'suspender'}')">
              ${isSuspended ? '▶ Reactivar' : '⏸ Suspender'}
            </button>
            <button type="button" class="action-btn-sm" style="color: #38bdf8; border-color: rgba(56,189,248,0.3);" onclick="impersonateBusiness(${biz.id})" title="Acceder al panel de este negocio">
              👁️ Entrar
            </button>
            <button type="button" class="action-btn-sm" onclick="openResetPasswordModal(${biz.id}, '${escapeHtml(biz.name)}')" title="Generar nueva clave">
              🔑 Clave
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function renderAuditLogs(logs) {
  const tbody = document.getElementById('auditTableBody');
  if (!logs || logs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 2rem; color: var(--text-muted);">Sin registros.</td></tr>`;
    return;
  }

  tbody.innerHTML = logs.map(log => {
    const dateFormatted = log.created_at ? new Date(log.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '--';
    let typeBadge = `<span style="font-size: 0.75rem; background: var(--bg-surface-elevated); padding: 0.15rem 0.5rem; border-radius: 4px; color: #38bdf8;">${log.log_type || 'alerta'}</span>`;

    return `
      <tr>
        <td style="font-size: 0.8rem; color: var(--text-secondary); white-space: nowrap;">${dateFormatted}</td>
        <td style="font-weight: 600; font-size: 0.85rem;">${escapeHtml(log.to_email)}</td>
        <td>${typeBadge}</td>
        <td style="font-size: 0.85rem; color: var(--text-primary);">${escapeHtml(log.subject)}</td>
        <td style="font-size: 0.8rem; color: var(--text-secondary); max-width: 320px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
          ${escapeHtml(log.body || '')}
        </td>
      </tr>
    `;
  }).join('');
}

// ---------------------------------------------------------------------------
// Admin Action Handlers & Modals
// ---------------------------------------------------------------------------

function openApproveModal(id, bizName) {
  document.getElementById('approveRequestId').value = id;
  document.getElementById('approveModalBizName').textContent = bizName;
  document.getElementById('initialPassword').value = '';
  document.getElementById('approveModalContent').style.display = 'block';
  document.getElementById('credentialsSuccessView').style.display = 'none';
  document.getElementById('approveModal').style.display = 'flex';
}

function closeApproveModal() {
  document.getElementById('approveModal').style.display = 'none';
  loadAdminRequests(activeRequestFilter);
}

function openRejectModal(id, bizName) {
  document.getElementById('rejectRequestId').value = id;
  document.getElementById('rejectModalBizName').textContent = bizName;
  document.getElementById('rejectModal').style.display = 'flex';
}

function closeRejectModal() {
  document.getElementById('rejectModal').style.display = 'none';
}

async function toggleBusinessStatus(id, actionText) {
  if (!confirm(`¿Estás seguro de que deseas ${actionText} este negocio?`)) return;

  try {
    const res = await adminFetch(`/api/admin/businesses/${id}/toggle-status`, { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.success) {
      loadAdminBusinesses();
      loadAdminStats();
    } else {
      alert(data.error || 'Error al cambiar estado.');
    }
  } catch (err) {
    alert('Error de conexión.');
  }
}

async function impersonateBusiness(id) {
  try {
    const res = await adminFetch(`/api/admin/businesses/${id}/impersonate`, { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.success) {
      if (data.token) {
        localStorage.setItem('session_token', data.token);
      }
      window.open('/dashboard', '_blank');
    } else {
      alert(data.error || 'Error al abrir sesión de negocio.');
    }
  } catch (err) {
    alert('Error de conexión.');
  }
}

function openResetPasswordModal(id, name) {
  document.getElementById('resetBusinessId').value = id;
  document.getElementById('resetBizName').textContent = name;
  document.getElementById('newCustomPassword').value = '';
  document.getElementById('resetPasswordResult').style.display = 'none';
  document.getElementById('resetPasswordModal').style.display = 'flex';
}

function closeResetPasswordModal() {
  document.getElementById('resetPasswordModal').style.display = 'none';
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
