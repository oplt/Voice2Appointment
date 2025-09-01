document.addEventListener('DOMContentLoaded', function () {
  const container = document.getElementById('calendarContainer');
  const agendaBtn = document.getElementById('agendaView');
  const weekBtn   = document.getElementById('weekView');
  const monthBtn  = document.getElementById('monthView');

  const TIMEZONE = 'Europe/Brussels';

  container.innerHTML = '<div id="fullcalendar"></div>';
  const calendarEl = document.getElementById('fullcalendar');

  const calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: 'dayGridMonth',
    timeZone: TIMEZONE,
    height: 'auto',
    expandRows: true,
    headerToolbar: {
      left: 'prev,next today',
      center: 'title',
      right: 'dayGridMonth,timeGridWeek,listWeek'
    },
    nowIndicator: true,
    navLinks: true,
    selectable: false,
    eventTimeFormat: { hour: '2-digit', minute: '2-digit', meridiem: false },
    eventDisplay: 'block',
    dayMaxEvents: true,
    moreLinkClick: 'popover',

    events: function(fetchInfo, successCallback, failureCallback) {
      console.log('Fetching events for:', fetchInfo.startStr, 'to', fetchInfo.endStr);
      
      const url = `/google/events?timeMin=${encodeURIComponent(fetchInfo.startStr)}&timeMax=${encodeURIComponent(fetchInfo.endStr)}&timezone=${encodeURIComponent(TIMEZONE)}`;
      
      fetch(url)
        .then(async (res) => {
          if (res.status === 401) {
            // User not authenticated with Google Calendar
            calendarEl.innerHTML = `
              <div class="p-4 text-center">
                <h5>Google Calendar not connected</h5>
                <p class="text-muted mb-3">Connect your Google account to see your calendar events here.</p>
                <a class="btn btn-primary" href="/google/connect">
                  <i class="fab fa-google me-1"></i> Connect Google Calendar
                </a>
              </div>`;
            return [];
          }
          if (!res.ok) {
            const errorText = await res.text();
            console.error('Failed to fetch events:', res.status, errorText);
            throw new Error(`HTTP ${res.status}: ${errorText}`);
          }
          return res.json();
        })
        .then((events) => {
          console.log('Events fetched successfully:', events.length, 'events');
          successCallback(events);
        })
        .catch((error) => {
          console.error('Error fetching events:', error);
          // Show error message in calendar
          calendarEl.innerHTML = `
            <div class="p-4 text-center">
              <h5>Failed to load calendar events</h5>
              <p class="text-danger mb-3">${error.message}</p>
              <button class="btn btn-outline-primary" onclick="location.reload()">
                <i class="fas fa-redo me-1"></i> Retry
              </button>
            </div>`;
          failureCallback(error);
        });
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
  
  // Set initial active button
  setActive(monthBtn);
  
  console.log('Calendar initialized and rendered');

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



  function setActive(btn) {
    [agendaBtn, weekBtn, monthBtn].forEach(b => b.classList.remove('btn-primary'));
    [agendaBtn, weekBtn, monthBtn].forEach(b => b.classList.add('btn-outline-primary'));
    btn.classList.remove('btn-outline-primary');
    btn.classList.add('btn-primary');
  }


  
  function updateWebSocketStatus(status) {
    // You can add UI elements to show the connection status
    console.log('WebSocket status:', status);
    
    // Example: Update a status indicator in your HTML
    const statusElement = document.getElementById('websocket-status');
    if (statusElement) {
      statusElement.textContent = `Voice Assistant: ${status}`;
      statusElement.className = `badge ${status === 'connected' ? 'bg-success' : status === 'error' ? 'bg-danger' : 'bg-warning'}`;
    }
  }
  
  function handleWebSocketMessage(data) {
    try {
      const message = JSON.parse(data);
      
      // Handle different types of messages from the voice assistant
      if (message.type === 'FunctionCallResponse') {
        console.log('Function call result:', message.content);
        // You can display the result in the UI
        displayVoiceAssistantResult(message.content);
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
    }
  }
  
  function displayVoiceAssistantResult(content) {
    // Display voice assistant results in the UI
    // You can customize this based on your needs
    const resultContainer = document.getElementById('voice-assistant-results');
    const resultsContainer = document.getElementById('voice-results-container');
    
    if (resultContainer && resultsContainer) {
      // Show the results container
      resultContainer.style.display = 'block';
      
      const resultElement = document.createElement('div');
      resultElement.className = 'alert alert-info mb-2';
      resultElement.textContent = content;
      resultsContainer.appendChild(resultElement);
      
      // Remove the result after 5 seconds
      setTimeout(() => {
        resultElement.remove();
        
        // Hide the container if no more results
        if (resultsContainer.children.length === 0) {
          resultContainer.style.display = 'none';
        }
      }, 5000);
    }
  }
  
  // Initialize WebSocket connection when dashboard loads
  connectWebSocket();

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
