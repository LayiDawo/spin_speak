const canvas = document.getElementById('wheel');
const ctx = canvas.getContext('2d');
const spinBtn = document.getElementById('spinBtn');
const resultDiv = document.getElementById('result');

let teams = [];
let startAngle = 0;
let arc = 0;
let spinTimeout = null;
let spinArcStart = 0;
let spinTime = 0;
let spinTimeTotal = 0;
let selectedTeamIndex = -1;

// Assume socket is globally available
// (initialized in spin.html before this script runs)

async function fetchTeams() {
  try {
    const res = await fetch('/get_teams');
    const allTeams = await res.json();
    teams = allTeams
      .map(t => t.team_name)
      .filter(name => !name.toLowerCase().includes('feedback'));

    if (teams.length === 0) {
      resultDiv.textContent = "No teams loaded. Check /get_teams response.";
    }

    arc = Math.PI * 2 / teams.length;
    drawWheel();
  } catch (e) {
    console.error('Error fetching teams:', e);
    resultDiv.textContent = "Error fetching teams from server.";
  }
}

function drawWheel() {
  const outsideRadius = 200;
  const textRadius = 160;
  const insideRadius = 50;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = 'black';
  ctx.lineWidth = 2;
  ctx.font = 'bold 16px Arial';

  for (let i = 0; i < teams.length; i++) {
    const angle = startAngle + i * arc;
    ctx.fillStyle = i % 2 === 0 ? '#007bff' : '#00aaff';

    ctx.beginPath();
    ctx.moveTo(canvas.width / 2, canvas.height / 2);
    ctx.arc(canvas.width / 2, canvas.height / 2, outsideRadius, angle, angle + arc, false);
    ctx.lineTo(canvas.width / 2, canvas.height / 2);
    ctx.fill();
    ctx.stroke();

    ctx.save();
    ctx.fillStyle = 'white';
    ctx.translate(
      canvas.width / 2 + Math.cos(angle + arc / 2) * textRadius,
      canvas.height / 2 + Math.sin(angle + arc / 2) * textRadius
    );
    ctx.rotate(angle + arc / 2 + Math.PI / 2);
    const text = teams[i];
    ctx.fillText(text, -ctx.measureText(text).width / 2, 0);
    ctx.restore();
  }

  // Draw center circle
  ctx.fillStyle = '#fff';
  ctx.beginPath();
  ctx.arc(canvas.width / 2, canvas.height / 2, insideRadius, 0, 2 * Math.PI);
  ctx.fill();
  ctx.stroke();

  // Draw pointer
  ctx.fillStyle = '#dc3545';
  ctx.beginPath();
  ctx.moveTo(canvas.width / 2 - 10, canvas.height / 2 - (outsideRadius + 10));
  ctx.lineTo(canvas.width / 2 + 10, canvas.height / 2 - (outsideRadius + 10));
  ctx.lineTo(canvas.width / 2, canvas.height / 2 - (outsideRadius - 20));
  ctx.closePath();
  ctx.fill();
}

function spinToIndex(index) {
  const degreesPerSlice = 360 / teams.length;
  const targetDegree = 360 * 5 + (index * degreesPerSlice) + degreesPerSlice / 2; 
  const startDeg = startAngle * 180 / Math.PI;
  const diff = targetDegree - startDeg;

  spinTime = 0;
  spinTimeTotal = 5000; // 5 seconds spin
  spinArcStart = diff;

  rotateWheel();
}

function rotateWheel() {
  spinTime += 30;
  if (spinTime >= spinTimeTotal) {
    stopRotateWheel();
    return;
  }
  const spinAngle = spinArcStart - easeOut(spinTime, 0, spinArcStart, spinTimeTotal);
  startAngle += (spinAngle * Math.PI / 180);
  drawWheel();
  spinTimeout = setTimeout(rotateWheel, 30);
}

function stopRotateWheel() {
  clearTimeout(spinTimeout);
  const degrees = startAngle * 180 / Math.PI + 90;
  const arcd = arc * 180 / Math.PI;
  let index = Math.floor((360 - (degrees % 360)) / arcd);
  index = index >= teams.length ? index % teams.length : index;
  selectedTeamIndex = index;

  resultDiv.textContent = `Selected Team: ${teams[selectedTeamIndex]}`;
  if (window.isAdmin) {
    spinBtn.disabled = false;
  }
}

function easeOut(t, b, c, d) {
  const ts = (t /= d) * t;
  const tc = ts * t;
  return b + c * (tc + -3 * ts + 3 * t);
}

// Only show spin button to admin
if (!window.isAdmin) {
  spinBtn.style.display = 'none';
} else {
  spinBtn.addEventListener('click', () => {
    spinBtn.disabled = true;
    resultDiv.textContent = 'Waiting for server...';

    socket.emit('start_spin');
  });
}

// Listen for spin result from server
socket.on('spin_result', (data) => {
  if (!teams.length) return;
  const chosenTeam = data.team;
  const chosenIndex = teams.findIndex(t => t === chosenTeam);
  if (chosenIndex === -1) {
    resultDiv.textContent = 'Error: chosen team not found on wheel.';
    if (window.isAdmin) spinBtn.disabled = false;
    return;
  }
  spinToIndex(chosenIndex);
});

// Load teams on page load
fetchTeams();
