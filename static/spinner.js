const spinBtn = document.getElementById('spinBtn');
const spinner = document.getElementById('spinner');
const roundDisplay = document.getElementById('round');
const removeBtn = document.getElementById('removeBtn');  // Make sure this exists in your HTML
let animationInterval = null;
let teams = [];
let userRole = 'participant';  // default role

// Initialize Socket.IO client
const socket = io();

function startSpinnerAnimation() {
  let i = 0;
  spinner.style.color = '#007bff';
  animationInterval = setInterval(() => {
    spinner.textContent = teams[i % teams.length];
    i++;
  }, 100);
}

function stopSpinnerAnimation(finalTeam) {
  clearInterval(animationInterval);
  spinner.style.color = '#28a745';
  spinner.textContent = `Selected Team: ${finalTeam}`;
  spinBtn.disabled = false;

  showRemoveTeamButton(finalTeam);
}

function showRemoveTeamButton(team) {
  removeBtn.style.display = 'inline-block';
  removeBtn.disabled = false;
  removeBtn.textContent = `Remove Team "${team}"`;

  removeBtn.onclick = async () => {
    removeBtn.disabled = true;
    try {
      const res = await fetch('/api/remove_team', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({team})
      });

      if (res.ok) {
        spinner.textContent = `Team "${team}" removed! Spin again.`;
        removeBtn.style.display = 'none';

        // Refresh teams list so spinner animation updates
        await fetchTeams();
      } else {
        spinner.textContent = 'Error removing team.';
        removeBtn.disabled = false;
      }
    } catch (e) {
      spinner.textContent = 'Error removing team.';
      removeBtn.disabled = false;
    }
  };
}

// Listen for spin result broadcasted from backend
socket.on('spin_result', (data) => {
  stopSpinnerAnimation(data.team);
});

// Listen for round reset
socket.on('round_reset', (data) => {
  roundDisplay.textContent = `Round: ${data.round}`;
  spinner.textContent = 'Round reset! Spin again...';
  spinner.style.color = '#333';
  spinBtn.disabled = false;
  removeBtn.style.display = 'none';
});

// When spin button clicked
spinBtn.addEventListener('click', () => {
  if (userRole !== 'admin') {
    alert("Sorry, only admins can spin the wheel.");
    return;
  }

  spinBtn.disabled = true;
  spinner.textContent = 'Spinning...';
  removeBtn.style.display = 'none'; // Hide remove button while spinning
  startSpinnerAnimation();

  // Notify backend to start spin and broadcast result
  socket.emit('start_spin');
});

async function fetchTeams() {
  try {
    const res = await fetch('/get_teams');
    const allTeams = await res.json();
    teams = allTeams
      .map(t => t.team_name)
      .filter(name => !name.toLowerCase().includes('feedback'));
  } catch (e) {
    spinner.textContent = "Error loading teams";
  }
}

async function fetchUserRole() {
  try {
    const res = await fetch('/get-role');
    const data = await res.json();
    userRole = data.role || 'participant';
    // Optionally you can log or show the role somewhere
  } catch (e) {
    console.error('Error fetching user role', e);
  }
}

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
  await fetchTeams();
  await fetchUserRole();
});
