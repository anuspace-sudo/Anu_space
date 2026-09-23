/* Main JS for Anu's Space */

document.addEventListener('DOMContentLoaded', function () {
  console.log("Anu's Space initialized.");

  // Fetch dynamic progress update if available
  const progressFill = document.getElementById('progressBarFill');
  const progressCounter = document.getElementById('progressCounterText');
  const progressPercent = document.getElementById('progressPercentageText');

  if (progressFill && progressCounter && progressPercent) {
    fetch('/api/progress')
      .then(res => res.json())
      .then(data => {
        if (data) {
          progressCounter.textContent = `${data.completed} / ${data.target} problems`;
          progressPercent.textContent = `${data.percent}%`;
          progressFill.style.width = `${data.percent}%`;
        }
      })
      .catch(err => console.log('API sync notice:', err));
  }
});
