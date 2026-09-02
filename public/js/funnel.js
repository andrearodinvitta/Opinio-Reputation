/**
 * Opinio / Reputation Shield - Client Review Funnel Controller
 * Ultralight, mobile-first experience (<50ms).
 */

let businessData = null;
let currentRating = 0;
let currentReviewId = null;
let countdownTimer = null;

const ratingLabels = {
  1: '😠 Muy insatisfecho',
  2: '🙁 Por debajo de lo esperado',
  3: '😐 Aceptable / Regular',
  4: '😊 ¡Muy buena experiencia!',
  5: '🤩 ¡Excelente, me encantó!'
};

document.addEventListener('DOMContentLoaded', () => {
  initFunnel();
  bindFunnelEvents();
});

function getSlugFromUrl() {
  const path = window.location.pathname;
  if (path.startsWith('/r/')) {
    return path.substring(3).split('/')[0];
  }
  if (path.startsWith('/feedback/')) {
    return path.substring(10).split('/')[0];
  }
  const params = new URLSearchParams(window.location.search);
  return params.get('slug') || 'soraya-nails';
}

async function initFunnel() {
  const slug = getSlugFromUrl();
  try {
    const res = await fetch(`/api/funnel/${slug}`);
    const data = await res.json();

    if (res.status === 403 && data.suspended) {
      document.getElementById('loadingStep').style.display = 'none';
      document.getElementById('suspendedBizName').textContent = data.business.name || 'Portal en mantenimiento';
      document.getElementById('suspendedStep').style.display = 'block';
      return;
    }

    if (res.ok && data.success && data.business) {
      businessData = data.business;
      applyBranding(businessData);
      document.getElementById('loadingStep').style.display = 'none';
      document.getElementById('ratingStep').style.display = 'block';
    } else {
      showError('Negocio no encontrado');
    }
  } catch (err) {
    showError('Error al conectar con el servidor.');
  }
}

function applyBranding(biz) {
  document.title = `Califica a ${biz.name}`;
  document.getElementById('bizName').textContent = biz.name;
  if (biz.welcome_title) {
    document.getElementById('bizPrompt').textContent = biz.welcome_title;
  }

  const logoEl = document.getElementById('bizLogo');
  if (biz.logo_url && biz.logo_url.startsWith('http')) {
    logoEl.innerHTML = `<img src="${biz.logo_url}" alt="${biz.name}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
  } else {
    const initials = biz.name.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();
    document.getElementById('bizInitials').textContent = initials || '⭐';
  }

  if (biz.primary_color) {
    document.documentElement.style.setProperty('--brand-primary', biz.primary_color);
  }
}

function bindFunnelEvents() {
  const starBtns = document.querySelectorAll('.star-btn');
  const ratingLabel = document.getElementById('ratingLabel');

  starBtns.forEach(btn => {
    const starVal = parseInt(btn.dataset.star);

    // Hover effect
    btn.addEventListener('mouseenter', () => {
      highlightStars(starVal);
      if (ratingLabels[starVal]) ratingLabel.textContent = ratingLabels[starVal];
    });

    // Click / Touch
    btn.addEventListener('click', () => {
      selectRating(starVal);
    });
  });

  const starsContainer = document.getElementById('starsContainer');
  if (starsContainer) {
    starsContainer.addEventListener('mouseleave', () => {
      if (currentRating > 0) {
        highlightStars(currentRating);
        ratingLabel.textContent = ratingLabels[currentRating];
      } else {
        highlightStars(0);
        ratingLabel.textContent = 'Toca las estrellas para calificar';
      }
    });
  }

  // Back / Change rating buttons
  const btnChange1 = document.getElementById('btnChangeRating1');
  if (btnChange1) btnChange1.addEventListener('click', resetToRatingStep);

  const btnChange2 = document.getElementById('btnChangeRating2');
  if (btnChange2) btnChange2.addEventListener('click', resetToRatingStep);

  // Negative Feedback Form Submit
  const feedbackForm = document.getElementById('feedbackForm');
  if (feedbackForm) {
    feedbackForm.addEventListener('submit', handleFeedbackSubmit);
  }
}

function highlightStars(count) {
  const starBtns = document.querySelectorAll('.star-btn');
  starBtns.forEach(btn => {
    const starVal = parseInt(btn.dataset.star);
    if (starVal <= count) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

async function selectRating(rating) {
  currentRating = rating;
  highlightStars(rating);

  const slug = getSlugFromUrl();

  // Send rating to server
  try {
    const res = await fetch(`/api/funnel/${slug}/rating`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating })
    });
    const data = await res.json();
    if (data.success) {
      currentReviewId = data.review_id;

      // FILTERING LOGIC
      if (rating >= 4) {
        // POSITIVE: Show Google flow
        showPositiveFlow(data.google_review_url || businessData.google_review_url);
      } else {
        // NEGATIVE: Show private interception form
        showNegativeFlow();
      }
    }
  } catch (err) {
    console.error('Error sending rating:', err);
    if (rating >= 4) {
      showPositiveFlow(businessData.google_review_url);
    } else {
      showNegativeFlow();
    }
  }
}

function showPositiveFlow(googleUrl) {
  document.getElementById('ratingStep').style.display = 'none';
  document.getElementById('negativeStep').style.display = 'none';
  document.getElementById('positiveStep').style.display = 'block';

  const defaultSearchQuery = encodeURIComponent((businessData && businessData.name ? businessData.name : 'negocio') + ' opiniones google');
  const targetUrl = (googleUrl && googleUrl.startsWith('http')) 
    ? googleUrl 
    : (businessData && businessData.google_review_url && businessData.google_review_url.startsWith('http'))
      ? businessData.google_review_url 
      : `https://www.google.com/search?q=${defaultSearchQuery}`;

  const redirectBtn = document.getElementById('googleRedirectBtn');
  if (redirectBtn) {
    redirectBtn.href = targetUrl;
    redirectBtn.onclick = (e) => {
      e.preventDefault();
      if (countdownTimer) clearInterval(countdownTimer);
      window.location.href = targetUrl;
    };
  }

  // Auto redirect countdown (2 seconds) with direct location navigation (no popup blocker)
  let timeLeft = 2;
  const countdownEl = document.getElementById('countdownSeconds');
  const countdownBox = document.getElementById('countdownBox');

  if (countdownTimer) clearInterval(countdownTimer);

  countdownTimer = setInterval(() => {
    timeLeft -= 1;
    if (countdownEl) countdownEl.textContent = timeLeft;
    if (timeLeft <= 0) {
      clearInterval(countdownTimer);
      if (countdownBox) countdownBox.innerHTML = `<span>✓ Redirigiendo a Google...</span>`;
      window.location.href = targetUrl;
    }
  }, 1000);
}

function showNegativeFlow() {
  if (countdownTimer) clearInterval(countdownTimer);
  document.getElementById('ratingStep').style.display = 'none';
  document.getElementById('positiveStep').style.display = 'none';
  document.getElementById('negativeStep').style.display = 'block';
}

function selectCategory(el, catName) {
  document.querySelectorAll('.category-pill').forEach(p => p.classList.remove('selected'));
  el.classList.add('selected');
  document.getElementById('feedbackCategory').value = catName;
}

function copyPraise(btn, text) {
  navigator.clipboard.writeText(text).then(() => {
    document.querySelectorAll('.suggested-chip').forEach(c => c.classList.remove('copied'));
    btn.classList.add('copied');
    const notice = document.getElementById('copyNotice');
    notice.style.display = 'block';
    setTimeout(() => {
      notice.style.display = 'none';
    }, 4000);
  });
}

async function handleFeedbackSubmit(e) {
  e.preventDefault();
  const slug = getSlugFromUrl();
  const comment = document.getElementById('feedbackComment').value.trim();
  const customer_name = document.getElementById('customerName').value.trim();
  const customer_contact = document.getElementById('customerContact').value.trim();
  const category = document.getElementById('feedbackCategory').value;
  const submitBtn = document.getElementById('submitFeedbackBtn');

  submitBtn.disabled = true;
  submitBtn.textContent = 'Enviando a la gerencia...';

  try {
    const res = await fetch(`/api/funnel/${slug}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        review_id: currentReviewId,
        comment,
        customer_name,
        customer_contact,
        category
      })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      document.getElementById('negativeStep').style.display = 'none';
      document.getElementById('successFeedbackStep').style.display = 'block';
    } else {
      alert(data.error || 'Error al enviar feedback.');
    }
  } catch (err) {
    alert('Error al enviar comentarios.');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Enviar comentarios a la gerencia';
  }
}

function resetToRatingStep() {
  if (countdownTimer) clearInterval(countdownTimer);
  document.getElementById('positiveStep').style.display = 'none';
  document.getElementById('negativeStep').style.display = 'none';
  document.getElementById('successFeedbackStep').style.display = 'none';
  document.getElementById('ratingStep').style.display = 'block';
}

function resetFunnel() {
  resetToRatingStep();
  highlightStars(0);
  currentRating = 0;
  document.getElementById('ratingLabel').textContent = 'Toca las estrellas para calificar';
}

function showError(msg) {
  document.getElementById('loadingStep').innerHTML = `
    <div style="font-size: 2rem; margin-bottom: 0.5rem;">⚠️</div>
    <p style="color: #ef4444; font-weight: 600;">${msg}</p>
    <a href="/" style="font-size: 0.82rem; color: #64748b; text-decoration: underline; margin-top: 1rem; display: inline-block;">Volver</a>
  `;
}
