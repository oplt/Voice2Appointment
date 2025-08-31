document.addEventListener('DOMContentLoaded', function () {
  const container = document.getElementById('calendarContainer');
  const agendaBtn = document.getElementById('agendaView');
  const weekBtn   = document.getElementById('weekView');
  const monthBtn  = document.getElementById('monthView');

  const TIMEZONE = 'Europe/Brussels';
  const CAL_ID   = 'polatozgur111@gmail.com';
  const BASE     = 'https://calendar.google.com/calendar/embed';
    const COMMON   = `src=${CAL_ID}&ctz=${encodeURIComponent(TIMEZONE)}&showTabs=1&showTitle=0&wkst=2`;

  const frame = document.getElementById('gcalFrame');

  container.innerHTML = '<div id="fullcalendar"></div>';
  const calendarEl = document.getElementById('fullcalendar');

  const calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: 'dayGridMonth',
    timeZone: TIMEZONE,
    height: 'auto',
    expandRows: true,
    headerToolbar: false,
    nowIndicator: true,
    navLinks: true,
    selectable: false,
    eventTimeFormat: { hour: '2-digit', minute: '2-digit', meridiem: false },

    events: function(fetchInfo, successCallback, failureCallback) {
      const url = `/google/events?timeMin=${encodeURIComponent(fetchInfo.startStr)}&timeMax=${encodeURIComponent(fetchInfo.endStr)}&timezone=${encodeURIComponent(TIMEZONE)}`;
      fetch(url)
        .then(async (res) => {
          if (res.status === 401) {
            calendarEl.innerHTML = `
              <div class="p-4">
                <h5>Google Calendar not connected</h5>
                <p class="text-muted">Connect your Google account to see your calendar here.</p>
                <a class="btn btn-primary" href="/google/connect">
                  <i class="fab fa-google me-1"></i> Connect Google Calendar
                </a>
              </div>`;
            return [];
          }
          if (!res.ok) throw new Error(await res.text());
          return res.json();
        })
        .then((events) => successCallback(events))
        .catch(failureCallback);
    },

    eventClick: function(info) {
      if (info.event.url) {
        info.jsEvent.preventDefault();
        window.open(info.event.url, '_blank');
      }
    },

    datesSet: function() {
      refreshCounts();
      refreshUpcoming();
    },
  });

  calendar.render();

  // Button handlers
  agendaBtn.addEventListener('click', () => {
    calendar.changeView('listWeek');
    setActive(agendaBtn);
  });
  weekBtn.addEventListener('click', () => {
    calendar.changeView('timeGridWeek');
    setActive(weekBtn);
  });
  monthBtn.addEventListener('click', () => {
    calendar.changeView('dayGridMonth');
    setActive(monthBtn);
  });

  function setMode(mode){ frame.src = `${BASE}?${COMMON}&mode=${mode}`; }
  setMode('MONTH');

    // hook your buttons
  document.getElementById('monthView').addEventListener('click', () => setMode('MONTH'));
  document.getElementById('weekView').addEventListener('click',  () => setMode('WEEK'));
  document.getElementById('agendaView').addEventListener('click',() => setMode('AGENDA'));

  function setActive(btn) {
    [agendaBtn, weekBtn, monthBtn].forEach(b => b.classList.remove('btn-primary'));
    [agendaBtn, weekBtn, monthBtn].forEach(b => b.classList.add('btn-outline-primary'));
    btn.classList.remove('btn-outline-primary');
    btn.classList.add('btn-primary');
  }

  function refreshCounts() {
    fetch('/google/counts')
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (!data) return;
        const todayEl = document.getElementById('todayCount');
        const weekEl = document.getElementById('weekCount');
        if (todayEl && data.today !== undefined) todayEl.textContent = data.today;
        if (weekEl && data.week !== undefined) weekEl.textContent = data.week;
      })
      .catch(console.error);
  }

  function refreshUpcoming() {
    const upcomingContainer = document.getElementById('upcomingAppointments');
    if (!upcomingContainer) return;

    const now = new Date().toISOString();
    const rangeEnd = calendar.view.currentEnd.toISOString();

    fetch(`/google/events?timeMin=${encodeURIComponent(now)}&timeMax=${encodeURIComponent(rangeEnd)}&timezone=${encodeURIComponent(TIMEZONE)}`)
      .then(res => res.ok ? res.json() : [])
      .then(events => {
        const next10 = events.slice(0, 10);
        if (next10.length === 0) {
          upcomingContainer.innerHTML = `
            <div class="text-muted text-center">
              <i class="far fa-smile-beam fa-2x mb-2"></i>
              <p>No upcoming appointments in this range.</p>
            </div>`;
          return;
        }
        upcomingContainer.innerHTML = next10.map(ev => {
          const start = new Date(ev.start);
          const end = ev.end ? new Date(ev.end) : null;
          const timeStr = ev.allDay
            ? 'All day'
            : `${start.toLocaleDateString()} ${start.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}` +
              (end ? ` – ${end.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}` : '');

          return `
            <div class="d-flex align-items-start mb-3">
              <i class="far fa-calendar-check me-3 mt-1"></i>
              <div>
                <div class="fw-bold">${ev.title || '(No title)'}</div>
                <div class="text-muted small">${timeStr}${ev.location ? ' · ' + ev.location : ''}</div>
                ${ev.url ? `<a href="${ev.url}" target="_blank" class="small">Open in Google Calendar</a>` : ''}
              </div>
            </div>
          `;
        }).join('');
      })
      .catch(err => {
        console.error(err);
        upcomingContainer.innerHTML = `
          <div class="text-danger small">Failed to load upcoming appointments.</div>`;
      });
  }
});
