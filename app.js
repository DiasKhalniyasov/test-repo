// Valid credentials
const VALID_USERNAME = 'user';
const VALID_PASSWORD = 'user';

document.addEventListener('DOMContentLoaded', function() {
  const form = document.getElementById('login-form');
  const usernameInput = document.getElementById('username');
  const passwordInput = document.getElementById('password');
  const statusMessage = document.getElementById('status-message');

  form.addEventListener('submit', function(event) {
    event.preventDefault();

    const username = usernameInput.value.trim();
    const password = passwordInput.value.trim();

    // Reset status
    statusMessage.className = 'status-message';
    statusMessage.textContent = '';

    // Validate empty fields
    if (!username || !password) {
      statusMessage.textContent = 'Please enter both username and password';
      statusMessage.classList.add('error');
      return;
    }

    // Check credentials
    if (username === VALID_USERNAME && password === VALID_PASSWORD) {
      statusMessage.textContent = 'You are logged in';
      statusMessage.classList.add('success');
    } else {
      statusMessage.textContent = 'Invalid username or password';
      statusMessage.classList.add('error');
    }
  });
});
