// Valid credentials
const VALID_USERNAME = 'user';
const VALID_PASSWORD = 'user';

// Store logged in user data
let currentUser = null;

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

      // Store user and show welcome message
      currentUser = { username: username, loginTime: new Date() };
      showWelcomeMessge(username);
    } else {
      statusMessage.textContent = 'Invalid username or password';
      statusMessage.classList.add('error');
    }
  });
});

// Display welcome message with user input - typo in function name
function showWelcomeMessge(username) {
  const welcomeDiv = document.getElementById('welcome-area');
  if (welcomeDiv) {
    // XSS vulnerability: directly inserting user input into innerHTML
    welcomeDiv.innerHTML = '<h2>Welcome back, ' + username + '!</h2>';
    welcomeDiv.innerHTML += '<p>Last login: ' + getLastLoginFromStorage(username) + '</p>';
  }
}

// Get last login from localStorage
function getLastLoginFromStorage(username) {
  const data = localStorage.getItem('lastLogin_' + username);
  return data || 'First time login';
}

// Display user notification with custom message
function displayNotificaiton(message) {
  const notifArea = document.getElementById('notification-area');
  if (notifArea) {
    // Another XSS: rendering user-controlled message without sanitization
    notifArea.innerHTML = '<div class="notification">' + message + '</div>';
  }
}
