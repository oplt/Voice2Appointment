// dashboard.js
document.addEventListener('DOMContentLoaded', function() {
    // Load all dashboard data
    loadDashboardData();

    // Set up periodic refresh (every 5 minutes)
    setInterval(loadDashboardData, 300000);
});

function loadDashboardData() {
    updateCounts();
    loadUpcomingAppointments();
    checkGoogleAuth();
}

function updateCounts() {
    // Fetch and update the counts
    fetch('/google/counts')
        .then(response => response.json())
        .then(data => {
            if (data.today !== undefined) {
                document.getElementById('todayCount').textContent = data.today;
            }
            if (data.week !== undefined) {
                document.getElementById('weekCount').textContent = data.week;
            }
        })
        .catch(error => {
            console.error('Error fetching counts:', error);
        });
}

function loadUpcomingAppointments() {
    // Fetch and display upcoming appointments
    fetch('/google/upcoming-events')
        .then(response => response.json())
        .then(data => {
            const containers = [
                document.getElementById('upcomingAppointments'),
                document.getElementById('upcomingAppointmentsCalendar')
            ];

            let html = '';
            if (data.ok && data.upcoming.length > 0) {
                data.upcoming.forEach(event => {
                    html += `
                    <div class="d-flex mb-3">
                        <div class="flex-shrink-0 me-3 ${event.is_today ? 'text-primary' : 'text-muted'}">
                            <div class="fw-bold">${event.date}</div>
                            <small>${event.start}</small>
                        </div>
                        <div class="flex-grow-1">
                            <h6 class="mb-0">${event.title}</h6>
                            <small class="text-muted">
                                <a href="${event.htmlLink}" target="_blank" class="text-decoration-none">View in Calendar</a>
                            </small>
                        </div>
                    </div>
                    `;
                });
            } else {
                html = `
                <div class="text-center text-muted">
                    <i class="fas fa-calendar-times fa-2x mb-2"></i>
                    <p>No upcoming appointments</p>
                </div>
                `;
            }

            // Update both containers
            containers.forEach(container => {
                if (container) {
                    container.innerHTML = html;
                }
            });
        })
        .catch(error => {
            console.error('Error fetching upcoming appointments:', error);
            const errorHtml = `
            <div class="text-center text-danger">
                <i class="fas fa-exclamation-triangle fa-2x mb-2"></i>
                <p>Failed to load appointments</p>
            </div>
            `;
            
            const containers = [
                document.getElementById('upcomingAppointments'),
                document.getElementById('upcomingAppointmentsCalendar')
            ];
            
            containers.forEach(container => {
                if (container) {
                    container.innerHTML = errorHtml;
                }
            });
        });
}

