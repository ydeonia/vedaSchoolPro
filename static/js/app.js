/* ============================================================
   EduFlow — App JavaScript
   Handles sidebar toggle, notifications, toasts, modals
   ============================================================ */

// --- Sidebar Scroll Persistence ---
(function(){
    const nav = document.querySelector('.sidebar-nav') || document.getElementById('sidebar');
    if(nav){
        const saved = sessionStorage.getItem('sidebarScroll');
        if(saved) nav.scrollTop = parseInt(saved);
        nav.addEventListener('scroll', ()=> sessionStorage.setItem('sidebarScroll', nav.scrollTop));
        // Also save on link click for immediate capture
        nav.querySelectorAll('a').forEach(a => a.addEventListener('click', ()=> sessionStorage.setItem('sidebarScroll', nav.scrollTop)));
    }
})();

// --- Sidebar Toggle ---
document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const menuToggle = document.getElementById('menuToggle');
    const sidebarClose = document.getElementById('sidebarClose');

    if (menuToggle) {
        menuToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });
    }

    if (sidebarClose) {
        sidebarClose.addEventListener('click', () => {
            sidebar.classList.remove('open');
        });
    }

    document.addEventListener('click', (e) => {
        if (sidebar && sidebar.classList.contains('open') &&
            !sidebar.contains(e.target) &&
            menuToggle && !menuToggle.contains(e.target)) {
            sidebar.classList.remove('open');
        }
    });
});

// --- Toast Notifications ---
function showToast(type, title, message, duration = 4000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const icons = {
        success: 'fa-check-circle',
        error: 'fa-times-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <i class="fas ${icons[type]} toast-icon"></i>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            ${message ? `<div class="toast-message">${message}</div>` : ''}
        </div>
        <button class="toast-close" onclick="this.closest('.toast').remove()">
            <i class="fas fa-times"></i>
        </button>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'toastSlideOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// --- Notification Panel ---
document.addEventListener('DOMContentLoaded', () => {
    const notifBtn = document.getElementById('notifBtn');
    const notifPanel = document.getElementById('notifPanel');
    const notifBadge = document.getElementById('notifBadge');
    const notifList = document.getElementById('notifList');

    if (notifBtn && notifPanel) {
        notifBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const isOpen = notifPanel.style.display !== 'none';
            notifPanel.style.display = isOpen ? 'none' : 'block';
            if (!isOpen) {
                try {
                    const result = await apiCall('/api/school/notifications/list?unread_only=false');
                    const notifs = result.notifications || [];
                    if (notifs.length === 0) {
                        notifList.innerHTML = '<div class="notif-empty"><i class="fas fa-bell-slash"></i><p>No new notifications</p></div>';
                    } else {
                        const ICONS = {attendance:'📋', fee_reminder:'💰', fee_received:'✅', result_published:'🏆', announcement:'📢', message:'💬', alert:'🔔'};
                        notifList.innerHTML = notifs.slice(0, 8).map(n => `
                            <div style="padding:10px 14px; border-bottom:1px solid var(--border-light); ${n.is_read ? '' : 'background:#F0F7FF;'} font-size:0.82rem; cursor:pointer;" onclick="window.location='${n.action_url || '/school/notifications'}'">
                                <div style="display:flex; gap:8px; align-items:center;">
                                    <span>${ICONS[n.type] || '🔔'}</span>
                                    <strong style="flex:1;">${n.title}</strong>
                                    <span style="font-size:0.68rem; color:var(--text-light);">${n.time}</span>
                                </div>
                                <div style="color:var(--text-secondary); font-size:0.78rem; margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${n.message}</div>
                            </div>
                        `).join('') + `<div style="text-align:center; padding:10px;"><a href="/school/notifications" style="font-size:0.78rem; color:var(--primary); font-weight:600;">View All Notifications →</a></div>`;
                    }
                } catch(e) {}
            }
        });

        document.addEventListener('click', (e) => {
            if (!notifPanel.contains(e.target) && e.target !== notifBtn && !notifBtn.contains(e.target)) {
                notifPanel.style.display = 'none';
            }
        });

        // Poll for unread count every 60s (skip for super admin)
        async function checkUnread() {
            if (window.location.pathname.startsWith('/super-admin')) return;
            try {
                const result = await apiCall('/api/school/notifications/unread-count');
                if (result.count > 0) {
                    notifBadge.textContent = result.count > 99 ? '99+' : result.count;
                    notifBadge.style.display = 'flex';
                } else {
                    notifBadge.style.display = 'none';
                }
            } catch(e) {}
        }
        checkUnread();
        setInterval(checkUnread, 60000);
    }
});

// --- Modal Handling ---
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }
}

document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.style.display = 'none';
        document.body.style.overflow = '';
    }
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay').forEach(m => {
            m.style.display = 'none';
        });
        document.body.style.overflow = '';
    }
});

// --- API Helper ---
async function apiCall(url, method = 'GET', data = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' },
    };

    if (data && method !== 'GET') {
        options.body = JSON.stringify(data);
    }

    try {
        const response = await fetch(url, options);
        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Something went wrong');
        }

        return result;
    } catch (error) {
        showToast('error', 'Error', error.message);
        throw error;
    }
}

// --- Confirm Dialog ---
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

// --- Form Utilities ---
function getFormData(formId) {
    const form = document.getElementById(formId);
    if (!form) return {};

    const formData = new FormData(form);
    const data = {};
    formData.forEach((value, key) => {
        data[key] = value;
    });
    return data;
}

// --- Attendance Quick Actions ---
function toggleAttendance(card) {
    const statuses = ['present', 'absent', 'late'];
    const currentStatus = statuses.find(s => card.classList.contains(s)) || '';
    const currentIndex = statuses.indexOf(currentStatus);
    const nextIndex = (currentIndex + 1) % statuses.length;

    statuses.forEach(s => card.classList.remove(s));
    card.classList.add(statuses[nextIndex]);

    const input = card.querySelector('input[type="hidden"]');
    if (input) {
        input.value = statuses[nextIndex];
    }

    const statusIcons = { present: '✅', absent: '❌', late: '⏰' };
    const statusEl = card.querySelector('.attendance-status');
    if (statusEl) {
        statusEl.textContent = statusIcons[statuses[nextIndex]];
    }
}

// --- Mark All Present ---
function markAllPresent() {
    document.querySelectorAll('.attendance-card').forEach(card => {
        const statuses = ['present', 'absent', 'late'];
        statuses.forEach(s => card.classList.remove(s));
        card.classList.add('present');

        const input = card.querySelector('input[type="hidden"]');
        if (input) input.value = 'present';

        const statusEl = card.querySelector('.attendance-status');
        if (statusEl) statusEl.textContent = '✅';
    });
    showToast('success', 'All Present', 'All students marked as present');
}

// --- Submit Attendance ---
async function submitAttendance(classId, sectionId, date) {
    const cards = document.querySelectorAll('.attendance-card');
    const records = [];

    cards.forEach(card => {
        const studentId = card.dataset.studentId;
        const status = ['present', 'absent', 'late'].find(s => card.classList.contains(s)) || 'present';
        records.push({ student_id: studentId, status: status });
    });

    try {
        await apiCall('/api/attendance/mark', 'POST', {
            class_id: classId,
            section_id: sectionId,
            date: date,
            records: records
        });
        showToast('success', 'Attendance Saved', `Attendance for ${records.length} students saved successfully`);
    } catch (error) {
        // Error already shown by apiCall
    }
}

// --- Delete Confirm ---
function deleteItem(url, itemName) {
    confirmAction(`Are you sure you want to delete ${itemName}? This action cannot be undone.`, async () => {
        try {
            await apiCall(url, 'DELETE');
            showToast('success', 'Deleted', `${itemName} has been deleted`);
            setTimeout(() => window.location.reload(), 800);
        } catch (error) {
            // Error already shown
        }
    });
}

// --- Search Filter (Client-side table filter) ---
document.addEventListener('DOMContentLoaded', () => {
    const globalSearch = document.getElementById('globalSearch');
    if (globalSearch) {
        globalSearch.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            const rows = document.querySelectorAll('.data-table tbody tr');

            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(query) ? '' : 'none';
            });
        });
    }
});

// --- Tab Switching ---
function switchTab(tabGroup, tabName) {
    // Hide all tab contents in group
    document.querySelectorAll(`[data-tab-group="${tabGroup}"]`).forEach(el => {
        el.style.display = 'none';
    });

    // Deactivate all tab buttons
    document.querySelectorAll(`[data-tab-btn="${tabGroup}"]`).forEach(btn => {
        btn.classList.remove('active');
    });

    // Show selected tab
    const tabContent = document.getElementById(`tab-${tabName}`);
    if (tabContent) tabContent.style.display = 'block';

    // Activate button
    const tabBtn = document.querySelector(`[data-tab-btn="${tabGroup}"][data-tab="${tabName}"]`);
    if (tabBtn) tabBtn.classList.add('active');
}

// --- File Upload Preview ---
function previewImage(input, previewId) {
    const preview = document.getElementById(previewId);
    if (!preview) return;

    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = (e) => {
            preview.src = e.target.result;
            preview.style.display = 'block';
        };
        reader.readAsDataURL(input.files[0]);
    }
}

// --- Print Helper ---
function printElement(elementId) {
    const element = document.getElementById(elementId);
    if (!element) return;

    const printWindow = window.open('', '_blank');
    printWindow.document.write(`
        <html>
        <head>
            <title>Print</title>
            <link rel="stylesheet" href="/static/css/style.css">
            <style>
                body { padding: 20px; background: white; }
                .no-print { display: none !important; }
            </style>
        </head>
        <body>${element.innerHTML}</body>
        </html>
    `);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => {
        printWindow.print();
        printWindow.close();
    }, 500);
}

// --- Number formatting (Indian) ---
function formatIndianCurrency(amount) {
    const num = parseFloat(amount);
    if (isNaN(num)) return '₹0';
    return '₹' + num.toLocaleString('en-IN');
}

// --- Date formatting ---
function formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}


// ============================================================
// DARK MODE
// ============================================================
function initTheme() {
    const saved = localStorage.getItem('eduflow-theme');
    if (saved === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
    updateThemeIcon();
}

function toggleTheme() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (isDark) {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('eduflow-theme', 'light');
    } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('eduflow-theme', 'dark');
    }
    updateThemeIcon();
}

function updateThemeIcon() {
    const btn = document.getElementById('themeToggle');
    if (!btn) return;
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    btn.innerHTML = isDark ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
    btn.setAttribute('data-tooltip', isDark ? 'Light mode' : 'Dark mode');
}

// Initialize theme before paint
initTheme();


// ============================================================
// CONFETTI — lightweight celebration
// ============================================================
function showConfetti(duration = 2000) {
    const canvas = document.createElement('canvas');
    canvas.className = 'confetti-burst';
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    document.body.appendChild(canvas);
    const ctx = canvas.getContext('2d');
    const colors = ['#4F46E5', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'];

    const particles = Array.from({ length: 80 }, () => ({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height * 0.3 - 50,
        size: Math.random() * 6 + 3,
        color: colors[Math.floor(Math.random() * colors.length)],
        vx: (Math.random() - 0.5) * 4,
        vy: Math.random() * 3 + 2,
        rotation: Math.random() * 360,
        rotSpeed: (Math.random() - 0.5) * 10,
        opacity: 1,
    }));

    const start = Date.now();
    function animate() {
        const elapsed = Date.now() - start;
        if (elapsed > duration) { canvas.remove(); return; }
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const fade = elapsed > duration * 0.7 ? 1 - (elapsed - duration * 0.7) / (duration * 0.3) : 1;
        particles.forEach(p => {
            p.x += p.vx;
            p.y += p.vy;
            p.vy += 0.08;
            p.rotation += p.rotSpeed;
            ctx.save();
            ctx.translate(p.x, p.y);
            ctx.rotate(p.rotation * Math.PI / 180);
            ctx.globalAlpha = fade;
            ctx.fillStyle = p.color;
            ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
            ctx.restore();
        });
        requestAnimationFrame(animate);
    }
    animate();
}


// ============================================================
// GAMIFICATION — Streaks & Achievements
// ============================================================
function showAchievement(emoji, title, subtitle) {
    const div = document.createElement('div');
    div.style.cssText = `
        position: fixed; top: 20px; right: 20px; z-index: 10000;
        background: white; border-radius: 16px; padding: 16px 20px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.15); display: flex; align-items: center; gap: 12px;
        animation: slideInRight 0.4s ease, fadeOut 0.3s ease 3.5s forwards;
        border: 2px solid #F59E0B; max-width: 340px;
    `;
    div.innerHTML = `
        <span style="font-size:2rem;">${emoji}</span>
        <div>
            <div style="font-weight:800; font-size:0.88rem; color:#1E293B;">${title}</div>
            <div style="font-size:0.75rem; color:#64748B;">${subtitle}</div>
        </div>
    `;
    document.body.appendChild(div);
    setTimeout(() => div.remove(), 4000);
}

// CSS animations for achievements
const achieveStyle = document.createElement('style');
achieveStyle.textContent = `
    @keyframes slideInRight { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
    @keyframes fadeOut { to { opacity: 0; transform: translateY(-10px); } }
`;
document.head.appendChild(achieveStyle);


// ============================================================
// SCROLL TO TOP
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    const scrollBtn = document.createElement('button');
    scrollBtn.className = 'scroll-top-btn';
    scrollBtn.innerHTML = '<i class="fas fa-arrow-up"></i>';
    scrollBtn.onclick = () => window.scrollTo({ top: 0, behavior: 'smooth' });
    document.body.appendChild(scrollBtn);

    const mainContent = document.querySelector('.main-content');
    if (mainContent) {
        mainContent.addEventListener('scroll', () => {
            scrollBtn.classList.toggle('visible', mainContent.scrollTop > 300);
        });
    }
    window.addEventListener('scroll', () => {
        scrollBtn.classList.toggle('visible', window.scrollY > 300);
    });
});