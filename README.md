# Frontend Tester - Local Test Environment

A simple login page for testing the frontend-tester agent locally.

## Quick Start

### 1. Install dependencies

```bash
cd agents/test

# Python dependencies
pip install -r requirements.txt

# Node.js serve (for hosting the page)
npm install -g serve
```

### 2. Set API key

```bash
export LLM_API_KEY="your-anthropic-api-key"
```

### 3. Run the test

```bash
python run_local_test.py
```

This will:
- Start the login page at `http://localhost:3000`
- Use LLM to identify test scenarios from the code
- Display scenarios that would be tested
- Keep server running for manual testing

### 4. Manual testing

Open `http://localhost:3000` in your browser:

| Username | Password | Expected Result |
|----------|----------|-----------------|
| user | user | "You are logged in" (green) |
| wrong | wrong | "Invalid username or password" (red) |
| (empty) | (empty) | "Please enter both username and password" (red) |

Press `Ctrl+C` to stop the server.

## Files

```
test/
├── package.json       # npm scripts (dev/start)
├── index.html         # Login form with data-testid attributes
├── style.css          # Form styling
├── app.js             # Login validation logic
├── requirements.txt   # Python dependencies
├── run_local_test.py  # Local test script
└── README.md          # This file
```

## Testing with Frontend-Tester Agent

To test with the actual frontend-tester agent in GitLab:

1. Create a new branch with changes to these files
2. Create an MR with title exactly: `AI-frontend-tester`
3. The CI pipeline will automatically run the frontend-tester

## Test Attributes

All interactive elements have `data-testid` attributes for Playwright:

- `data-testid="login-form"` - The form element
- `data-testid="username"` - Username input
- `data-testid="password"` - Password input
- `data-testid="login-button"` - Submit button
- `data-testid="status-message"` - Result message container
