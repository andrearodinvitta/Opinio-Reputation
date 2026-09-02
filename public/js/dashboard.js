/**
 * Opinio / Reputation Shield - Business Dashboard Controller
 * Handles analytics, private feedback resolution (WhatsApp/Call), QR stand designer, and branding.
 */

let currentBusiness = null;
let currentReviews = [];
let activeReviewFilter = 'all';

function getAuthHeader() {
  const token = localStorage.getItem('session_token');
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

async function authFetch(url, options = {}) {
  options.headers = {
    ...getAuthHeader(),
    ...(options.headers || {})
  };
  return fetch(url, options);
}

document.addEventListener('DOMContentLoaded', () => {
  initDashboard();
});

async function initDashboard() {
  await loadBusinessProfile();
  if (!currentBusiness) return;

  initNavigation();
  initSettingsForm();
  loadStats();
  loadReviews();
  loadEmailLogs();
  initQrStudio();
}

// ---------------------------------------------------------------------------
// Profile & Auth
// ---------------------------------------------------------------------------

async function loadBusinessProfile() {
  try {
    const res = await authFetch('/api/business/profile');
    if (!res.ok) {
      window.location.href = '/login';
      return;
    }
    const data = await res.json();
    if (data.success && data.business) {
      currentBusiness = data.business;
      renderSidebarProfile(currentBusiness);
    } else {
      window.location.href = '/login';
    }
  } catch (err) {
    console.error('Error fetching profile:', err);
    window.location.href = '/login';
  }
}

function renderSidebarProfile(biz) {
  document.getElementById('sideBusinessName').textContent = biz.name;
  document.getElementById('sideUserName').textContent = biz.name;
  document.getElementById('sideUserSlug').textContent = `/r/${biz.slug}`;

  const avatar = document.getElementById('sideUserAvatar');
  if (avatar) {
    const initial = biz.name ? biz.name.trim()[0].toUpperCase() : 'O';
    avatar.textContent = initial;
  }

  const liveFunnelBtn = document.getElementById('btnViewLiveFunnel');
  if (liveFunnelBtn) {
    liveFunnelBtn.href = `/r/${biz.slug}`;
  }

  const quickShareBtn = document.getElementById('btnQuickShare');
  if (quickShareBtn) {
    quickShareBtn.onclick = () => {
      const fullUrl = `${window.location.origin}/r/${biz.slug}`;
      navigator.clipboard.writeText(fullUrl);
      alert(`¡Enlace copiado al portapapeles!\n${fullUrl}`);
    };
  }

  // Populate settings form values
  document.getElementById('settingName').value = biz.name || '';
  document.getElementById('settingGoogleUrl').value = biz.google_review_url || '';
  document.getElementById('settingPrimaryColor').value = biz.primary_color || '#4F46E5';
  document.getElementById('settingPrimaryColorPicker').value = biz.primary_color || '#4F46E5';
  document.getElementById('settingAccentColor').value = biz.accent_color || '#EC4899';
  document.getElementById('settingAccentColorPicker').value = biz.accent_color || '#EC4899';
  document.getElementById('settingWelcomeTitle').value = biz.welcome_title || '';
  document.getElementById('settingNotificationEmail').value = biz.notification_email || biz.email || '';
  document.getElementById('settingNotifyOnNegative').checked = !!biz.notify_on_negative;

  // Set NFC URL input & QR code using public production URL by default
  updateNfcAndQrDisplays();

  const btnCopyNfc = document.getElementById('btnCopyNfcUrl');
  if (btnCopyNfc) {
    btnCopyNfc.onclick = () => {
      const currentUrl = getEffectivePublicUrl();
      navigator.clipboard.writeText(currentUrl);
      const toast = document.getElementById('copyNfcToast');
      if (toast) {
        toast.style.display = 'block';
        setTimeout(() => toast.style.display = 'none', 3500);
      }
    };
  }

  // Update Printable Stand Card
  document.getElementById('printBizName').textContent = biz.name;
  document.getElementById('printBizAvatar').textContent = biz.name ? biz.name.trim()[0].toUpperCase() : '⭐';
  if (biz.welcome_title) {
    document.getElementById('printSubtitle').textContent = biz.welcome_title;
  }

  // Update simulator iframe
  updateMobileSimulator();
}

// ---------------------------------------------------------------------------
// Navigation Tabs
// ---------------------------------------------------------------------------

function initNavigation() {
  const navLinks = document.querySelectorAll('.nav-link');
  navLinks.forEach(link => {
    link.addEventListener('click', () => {
      const tab = link.dataset.tab;
      switchTab(tab);
    });
  });

  const logoutBtn = document.getElementById('btnLogout');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', async () => {
      await authFetch('/api/auth/logout', { method: 'POST' });
      localStorage.removeItem('session_token');
      window.location.href = '/login';
    });
  }
}

function switchTab(tabName) {
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  document.querySelectorAll('.dashboard-tab-content').forEach(c => c.style.display = 'none');

  const activeNav = document.querySelector(`.nav-link[data-tab="${tabName}"]`);
  if (activeNav) activeNav.classList.add('active');

  const targetTab = document.getElementById(`tab-${tabName}`);
  if (targetTab) targetTab.style.display = 'block';

  // Update header titles
  const titles = {
    overview: 'Resumen de Reputación',
    reviews: 'Buzón Privado & Feedback',
    nfc: 'Cartelería QR & Enlace NFC',
    settings: 'Personalización de Marca',
    emails: 'Alertas por Email'
  };
  const descs = {
    overview: 'Monitorea y protege la reputación de tu negocio en Google en tiempo real.',
    reviews: 'Gestiona los comentarios de clientes y resuelve reclamos en privado.',
    nfc: 'Genera carteles para mesa y placas inteligentes NFC.',
    settings: 'Configura tus colores corporativos, enlace de Google y textos del embudo.',
    emails: 'Historial de alertas despachadas ante calificaciones de 1 a 3 estrellas.'
  };
  if (titles[tabName]) document.getElementById('pageTitle').textContent = titles[tabName];
  if (descs[tabName]) document.getElementById('pageDescription').textContent = descs[tabName];

  if (tabName === 'reviews') loadReviews();
  if (tabName === 'emails') loadEmailLogs();
  if (tabName === 'overview') loadStats();
}

// ---------------------------------------------------------------------------
// Stats & Overview
// ---------------------------------------------------------------------------

async function loadStats() {
  try {
    const res = await authFetch('/api/business/stats');
    if (!res.ok) return;
    const data = await res.json();
    if (data.success && data.stats) {
      renderStats(data.stats);
    }
  } catch (err) {
    console.error('Error fetching stats:', err);
  }
}

function renderStats(stats) {
  document.getElementById('kpiTotalRatings').textContent = stats.total_ratings || 0;
  document.getElementById('kpiSatisfactionRate').textContent = `${stats.satisfaction_rate || 100}%`;
  document.getElementById('kpiPositiveCount').textContent = stats.positive_count || 0;
  document.getElementById('kpiDivertedCount').textContent = stats.diverted_negative_count || 0;
  document.getElementById('kpiAvgRating').textContent = `Promedio: ${stats.average_rating || 5.0} ★`;

  const pendingBadge = document.getElementById('pendingReviewsBadge');
  if (stats.pending_attention > 0) {
    pendingBadge.style.display = 'inline-block';
    pendingBadge.textContent = stats.pending_attention;
  } else {
    pendingBadge.style.display = 'none';
  }

  // Distribution Bars
  const dist = stats.distribution || {};
  const total = stats.total_ratings || 1;

  for (let i = 1; i <= 5; i++) {
    const count = dist[i] || 0;
    const pct = Math.round((count / total) * 100);
    const bar = document.getElementById(`bar${i}`);
    const countEl = document.getElementById(`count${i}`);
    if (bar) bar.style.width = `${pct}%`;
    if (countEl) countEl.textContent = count;
  }
}

// ---------------------------------------------------------------------------
// Reviews Feed Management
// ---------------------------------------------------------------------------

async function loadReviews() {
  const container = document.getElementById('reviewsFeedContainer');
  container.innerHTML = `<p style="color: var(--text-muted); padding: 2rem 0; text-align: center;">Cargando opiniones...</p>`;

  try {
    const res = await authFetch('/api/business/reviews');
    if (!res.ok) throw new Error('Error al cargar reviews');
    const data = await res.json();
    currentReviews = data.reviews || [];
    renderReviewsFeed();
    renderUrgentFeedback();
  } catch (err) {
    container.innerHTML = `<p style="color: var(--danger); padding: 2rem 0;">Error al cargar las opiniones.</p>`;
  }
}

function renderReviewsFeed() {
  const container = document.getElementById('reviewsFeedContainer');
  let filtered = currentReviews;

  if (activeReviewFilter === 'positive') {
    filtered = currentReviews.filter(r => r.sentiment === 'positive');
  } else if (activeReviewFilter === 'negative') {
    filtered = currentReviews.filter(r => r.sentiment === 'negative');
  } else if (['new', 'contacted', 'resolved'].includes(activeReviewFilter)) {
    filtered = currentReviews.filter(r => r.status === activeReviewFilter);
  }

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="background: var(--bg-surface); padding: 3rem; text-align: center; border-radius: var(--radius-lg); border: 1px solid var(--border-color);">
        <div style="font-size: 2.5rem; margin-bottom: 0.75rem;">📭</div>
        <h3 style="font-size: 1.1rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.3rem;">No hay opiniones en este filtro</h3>
        <p style="color: var(--text-secondary); font-size: 0.85rem;">Comparte tu cartel QR para empezar a recibir valoraciones.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(r => createReviewCardHtml(r)).join('');
  bindReviewCardEvents();
}

function createReviewCardHtml(r) {
  const dateFormatted = r.created_at ? new Date(r.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '--';
  const isPositive = r.sentiment === 'positive';
  const starsDisplay = '★'.repeat(r.rating) + '☆'.repeat(5 - r.rating);

  const cleanPhone = r.customer_contact ? r.customer_contact.replace(/[^0-9+]/g, '') : '';
  const customerName = r.customer_name || 'Cliente';
  const bizName = currentBusiness ? currentBusiness.name : 'nuestro negocio';
  const categoryText = r.category || 'tu visita';

  // Empathetic prefilled WhatsApp template
  const defaultWaMsg = `Hola ${customerName}, soy el responsable de ${bizName}. He leído tu comentario sobre "${categoryText}" en nuestro buzón privado de satisfacción y me gustaría disculparme personalmente y compensarte. ¿Cómo podemos ayudarte?`;
  const whatsappUrl = cleanPhone ? `https://wa.me/${cleanPhone.replace('+', '')}?text=${encodeURIComponent(defaultWaMsg)}` : '#';

  const statusBadges = {
    new: '<span class="status-chip pending">🔴 Nuevo</span>',
    contacted: '<span class="status-chip warning">🟡 Contactado</span>',
    resolved: '<span class="status-chip approved">🟢 Resuelto</span>'
  };

  return `
    <div class="review-card" data-id="${r.id}" style="background: var(--bg-surface); border: 1px solid var(--border-color); border-radius: var(--radius-lg); padding: 1.5rem; margin-bottom: 1.25rem;">
      <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem;">
        <div style="display: flex; align-items: center; gap: 0.75rem;">
          <span style="font-size: 1.2rem; font-weight: 800; color: ${isPositive ? '#fbbf24' : '#f87171'};">${starsDisplay}</span>
          <span style="font-size: 0.8rem; background: var(--bg-surface-elevated); padding: 0.2rem 0.5rem; border-radius: 4px; color: var(--text-secondary); font-weight: 600;">
            ${r.category || 'General'}
          </span>
          ${!isPositive ? (statusBadges[r.status] || '') : '<span class="status-chip approved">Google Review</span>'}
        </div>
        <span style="font-size: 0.78rem; color: var(--text-muted);">${dateFormatted}</span>
      </div>

      <div style="margin-bottom: 0.75rem;">
        <div style="font-weight: 700; font-size: 0.95rem; color: var(--text-primary); display: flex; align-items: center; gap: 0.5rem;">
          <span>👤 ${escapeHtml(r.customer_name || 'Cliente anónimo')}</span>
          ${r.customer_contact ? `<span style="font-size: 0.8rem; font-weight: 400; color: #38bdf8;">(${escapeHtml(r.customer_contact)})</span>` : ''}
        </div>
        ${r.comment ? `<div class="review-comment" style="margin-top: 0.5rem;">"${escapeHtml(r.comment)}"</div>` : '<div style="font-size: 0.82rem; color: var(--text-muted); margin-top: 0.3rem;">(Sin comentario adicional escrito)</div>'}
      </div>

      ${!isPositive ? `
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem; border-top: 1px solid var(--border-color); padding-top: 0.85rem; margin-top: 0.85rem;">
          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
            ${cleanPhone ? `
              <a href="${whatsappUrl}" target="_blank" class="action-btn-sm action-btn-whatsapp" title="Abrir chat de WhatsApp con plantilla personalizada">
                💬 Resolver por WhatsApp
              </a>
            ` : ''}
            ${r.customer_contact && !cleanPhone.startsWith('+') ? `
              <a href="tel:${r.customer_contact}" class="action-btn-sm">
                📞 Llamar
              </a>
            ` : ''}
          </div>

          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <label style="font-size: 0.78rem; color: var(--text-muted);">Estado:</label>
            <select class="form-input status-select" data-id="${r.id}" style="padding: 0.25rem 0.5rem; font-size: 0.8rem; width: auto; background: var(--bg-surface-elevated);">
              <option value="new" ${r.status === 'new' ? 'selected' : ''}>🔴 Pendiente</option>
              <option value="contacted" ${r.status === 'contacted' ? 'selected' : ''}>🟡 Contactado</option>
              <option value="resolved" ${r.status === 'resolved' ? 'selected' : ''}>🟢 Resuelto</option>
            </select>
          </div>
        </div>
      ` : ''}
    </div>
  `;
}

function bindReviewCardEvents() {
  // Filter tabs
  const filterTabs = document.querySelectorAll('.filter-tab');
  filterTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      filterTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      activeReviewFilter = tab.dataset.filter || tab.dataset.status || 'all';
      renderReviewsFeed();
    });
  });

  // Status selects
  const selects = document.querySelectorAll('.status-select');
  selects.forEach(sel => {
    sel.addEventListener('change', async (e) => {
      const reviewId = sel.dataset.id;
      const newStatus = e.target.value;
      try {
        await authFetch(`/api/business/reviews/${reviewId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: newStatus })
        });
        const match = currentReviews.find(r => r.id == reviewId);
        if (match) match.status = newStatus;
        loadStats();
      } catch (err) {
        console.error('Error updating review status:', err);
      }
    });
  });
}

function renderUrgentFeedback() {
  const container = document.getElementById('urgentFeedbackList');
  const urgent = currentReviews.filter(r => r.sentiment === 'negative' && r.status === 'new').slice(0, 3);

  if (urgent.length === 0) {
    container.innerHTML = `
      <div style="padding: 1.5rem; text-align: center; color: var(--success); font-size: 0.88rem; font-weight: 600;">
        🎉 ¡Excelente! No tienes feedback negativo pendiente por resolver.
      </div>
    `;
    return;
  }

  container.innerHTML = urgent.map(r => `
    <div style="background: var(--bg-surface-elevated); border-left: 3px solid #ef4444; border-radius: var(--radius-sm); padding: 0.75rem 1rem; margin-bottom: 0.6rem;">
      <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.2rem;">
        <span style="font-weight: 700; color: #ef4444;">${'★'.repeat(r.rating)} ${escapeHtml(r.customer_name || 'Cliente')}</span>
        <span>${r.category || 'General'}</span>
      </div>
      <div style="font-size: 0.85rem; color: var(--text-primary); font-style: italic;">"${escapeHtml(r.comment || 'Sin comentario')}"</div>
    </div>
  `).join('');
}

// ---------------------------------------------------------------------------
// QR Studio & Table Tent Stand (Smart Domain Resolution)
// ---------------------------------------------------------------------------

let selectedDomainMode = 'vercel';
let customDomainValue = '';

function getEffectivePublicUrl() {
  if (!currentBusiness) return '';
  const slug = currentBusiness.slug;
  const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

  if (!isLocal) {
    // If deployed on Vercel or public domain, use active origin
    return `${window.location.origin}/r/${slug}`;
  }

  // If viewing on localhost on Mac
  if (selectedDomainMode === 'vercel') {
    return `https://opinio-reputation.vercel.app/r/${slug}`;
  } else if (selectedDomainMode === 'local') {
    const localIp = (currentBusiness && currentBusiness.local_base_url) ? currentBusiness.local_base_url : 'http://192.168.1.34:8080';
    return `${localIp}/r/${slug}`;
  } else if (selectedDomainMode === 'custom' && customDomainValue) {
    let base = customDomainValue.trim().replace(/\/+$/, '');
    if (!base.startsWith('http://') && !base.startsWith('https://')) {
      base = 'https://' + base;
    }
    return `${base}/r/${slug}`;
  }

  return `https://opinio-reputation.vercel.app/r/${slug}`;
}

function setDomainMode(mode) {
  selectedDomainMode = mode;
  
  const btnVercel = document.getElementById('btnModeVercel');
  const btnLocal = document.getElementById('btnModeLocal');
  const btnCustom = document.getElementById('btnModeCustom');
  const customBox = document.getElementById('customDomainBox');

  [btnVercel, btnLocal, btnCustom].forEach(b => {
    if (b) {
      b.className = 'btn-secondary';
      b.style.background = '';
      b.style.color = '';
    }
  });

  if (mode === 'vercel' && btnVercel) {
    btnVercel.className = 'btn-primary';
    btnVercel.style.background = 'linear-gradient(135deg, #4f46e5, #ec4899)';
    if (customBox) customBox.style.display = 'none';
  } else if (mode === 'local' && btnLocal) {
    btnLocal.className = 'btn-primary';
    btnLocal.style.background = 'linear-gradient(135deg, #059669, #10b981)';
    if (customBox) customBox.style.display = 'none';
  } else if (mode === 'custom' && btnCustom) {
    btnCustom.className = 'btn-primary';
    btnCustom.style.background = 'linear-gradient(135deg, #2563eb, #38bdf8)';
    if (customBox) customBox.style.display = 'block';
  }

  updateNfcAndQrDisplays();
}

function handleCustomDomainChange(val) {
  customDomainValue = val;
  updateNfcAndQrDisplays();
}

function updateNfcAndQrDisplays() {
  if (!currentBusiness) return;
  const effectiveUrl = getEffectivePublicUrl();

  // 1. NFC input
  const nfcInput = document.getElementById('nfcPublicUrlInput');
  if (nfcInput) nfcInput.value = effectiveUrl;

  // 2. Printable Table Tent short URL
  const printUrl = document.getElementById('printShortUrl');
  if (printUrl) {
    try {
      const parsed = new URL(effectiveUrl);
      printUrl.textContent = `${parsed.host}/r/${currentBusiness.slug}`;
    } catch(e) {
      printUrl.textContent = effectiveUrl;
    }
  }

  // 3. QR Studio
  initQrStudio();
}

function initQrStudio() {
  if (!currentBusiness) return;
  const qrContainer = document.getElementById('qrCanvasContainer');
  if (qrContainer) {
    const fullFunnelUrl = getEffectivePublicUrl();
    qrContainer.innerHTML = '';
    
    if (typeof QRCode !== 'undefined') {
      try {
        new QRCode(qrContainer, {
          text: fullFunnelUrl,
          width: 170,
          height: 170,
          colorDark: "#0f172a",
          colorLight: "#ffffff",
          correctLevel: QRCode.CorrectLevel.H
        });
        return;
      } catch (e) {
        console.warn('QRCode JS render error, falling back to image:', e);
      }
    }

    qrContainer.innerHTML = `
      <img src="https://api.qrserver.com/v1/create-qr-code/?size=170x170&margin=0&data=${encodeURIComponent(fullFunnelUrl)}" alt="Código QR" style="width: 170px; height: 170px; display: block;" onerror="this.onerror=null; this.src='/api/funnel/${currentBusiness.slug}/qr.svg';">
    `;
  }
}

// ---------------------------------------------------------------------------
// Settings & Live Mobile Simulator
// ---------------------------------------------------------------------------

function initSettingsForm() {
  const form = document.getElementById('settingsForm');
  if (form) {
    form.addEventListener('submit', handleSettingsSubmit);
  }

  // Live color pickers
  const primaryColorPicker = document.getElementById('settingPrimaryColorPicker');
  const primaryColorInput = document.getElementById('settingPrimaryColor');
  if (primaryColorPicker && primaryColorInput) {
    primaryColorPicker.addEventListener('input', (e) => {
      primaryColorInput.value = e.target.value;
      updateMobileSimulator();
    });
    primaryColorInput.addEventListener('input', (e) => {
      primaryColorPicker.value = e.target.value;
      updateMobileSimulator();
    });
  }

  const nameInput = document.getElementById('settingName');
  if (nameInput) {
    nameInput.addEventListener('input', () => {
      document.getElementById('printBizName').textContent = nameInput.value;
    });
  }
}

async function handleSettingsSubmit(e) {
  e.preventDefault();
  const name = document.getElementById('settingName').value.trim();
  const google_review_url = document.getElementById('settingGoogleUrl').value.trim();
  const primary_color = document.getElementById('settingPrimaryColor').value.trim();
  const accent_color = document.getElementById('settingAccentColor').value.trim();
  const welcome_title = document.getElementById('settingWelcomeTitle').value.trim();
  const notification_email = document.getElementById('settingNotificationEmail').value.trim();
  const notify_on_negative = document.getElementById('settingNotifyOnNegative').checked;
  const btn = document.getElementById('btnSaveSettings');
  const statusEl = document.getElementById('settingsSaveStatus');

  btn.disabled = true;
  btn.textContent = 'Guardando...';

  try {
    const res = await authFetch('/api/business/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        google_review_url,
        primary_color,
        accent_color,
        welcome_title,
        notification_email,
        notify_on_negative
      })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      statusEl.style.display = 'inline';
      setTimeout(() => { statusEl.style.display = 'none'; }, 3000);
      loadBusinessProfile();
    } else {
      alert(data.error || 'Error al guardar.');
    }
  } catch (err) {
    alert('Error al conectar con el servidor.');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Guardar Configuración';
  }
}

function updateMobileSimulator() {
  if (!currentBusiness) return;
  const iframe = document.getElementById('mobilePreviewFrame');
  if (iframe) {
    iframe.src = `/r/${currentBusiness.slug}?preview=1`;
  }
}

function testGoogleLink() {
  const url = document.getElementById('settingGoogleUrl').value.trim();
  if (url) {
    window.open(url, '_blank');
  } else {
    alert('Por favor introduce primero tu enlace de Google Reviews.');
  }
}

// ---------------------------------------------------------------------------
// Email Logs
// ---------------------------------------------------------------------------

async function loadEmailLogs() {
  const container = document.getElementById('emailLogsContainer');
  if (!container) return;

  try {
    const res = await authFetch('/api/business/email-logs');
    if (!res.ok) return;
    const data = await res.json();
    const logs = data.logs || [];

    if (logs.length === 0) {
      container.innerHTML = `<p style="color: var(--text-muted); font-size: 0.88rem;">No hay alertas de feedback negativo despachadas todavía.</p>`;
      return;
    }

    container.innerHTML = logs.map(l => {
      const dateFormatted = l.created_at ? new Date(l.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '--';
      return `
        <div style="background: var(--bg-surface-elevated); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 1rem; margin-bottom: 0.75rem;">
          <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.3rem;">
            <span>Enviado a: <strong style="color: var(--text-primary);">${escapeHtml(l.to_email)}</strong></span>
            <span>${dateFormatted}</span>
          </div>
          <div style="font-weight: 700; font-size: 0.9rem; color: #f87171; margin-bottom: 0.4rem;">${escapeHtml(l.subject)}</div>
          <pre style="font-family: inherit; font-size: 0.82rem; color: var(--text-secondary); white-space: pre-wrap; line-height: 1.4; background: rgba(0,0,0,0.2); padding: 0.6rem; border-radius: 6px;">${escapeHtml(l.body)}</pre>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error('Error loading email logs:', err);
  }
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
