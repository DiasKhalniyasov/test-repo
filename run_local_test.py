#!/usr/bin/env python3
"""
Local test script for frontend-tester agent.

This script tests the frontend-tester locally without requiring a GitLab MR.
It mocks the GitLab API responses and runs the agent against the local test app.

Usage:
    cd agents
    python -m test.run_local_test

    OR

    cd agents/test
    python run_local_test.py

Requirements:
    - Install dependencies: pip install -r ../requirements.txt
    - Set LLM_API_KEY environment variable
    - npm/npx available for serving the test app
"""

import os
import sys
import json
import asyncio
import subprocess
import signal
from pathlib import Path

# Add parent directory to path for imports BEFORE any other imports
agents_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(agents_dir))

# Check dependencies before importing
def check_dependencies():
    """Check that required packages are installed."""
    missing = []
    try:
        import litellm
    except ImportError:
        missing.append('litellm')
    try:
        import httpx
    except ImportError:
        missing.append('httpx')

    if missing:
        print("Error: Missing required packages:", ', '.join(missing))
        print("\nInstall dependencies with:")
        print(f"  cd {agents_dir}")
        print("  pip install -r requirements.txt")
        sys.exit(1)

check_dependencies()

from core.config import LLMConfig
from core.llm import acompletion
from prompts.frontend_tester import (
    build_scenario_identification_prompt,
)


# Mock diff representing changes to the login page
MOCK_DIFF = """diff --git a/index.html b/index.html
new file mode 100644
--- /dev/null
+++ b/index.html
@@ -0,0 +1,45 @@
+<!DOCTYPE html>
+<html lang="en">
+<head>
+  <meta charset="UTF-8">
+  <title>Login Page</title>
+</head>
+<body>
+  <div class="login-container">
+    <h1>Login</h1>
+    <form id="login-form" data-testid="login-form">
+      <input type="text" id="username" data-testid="username" placeholder="Enter username">
+      <input type="password" id="password" data-testid="password" placeholder="Enter password">
+      <button type="submit" data-testid="login-button">Login</button>
+    </form>
+    <div id="status-message" data-testid="status-message"></div>
+  </div>
+</body>
+</html>

diff --git a/app.js b/app.js
new file mode 100644
--- /dev/null
+++ b/app.js
@@ -0,0 +1,20 @@
+const VALID_USERNAME = 'user';
+const VALID_PASSWORD = 'user';
+
+document.addEventListener('DOMContentLoaded', function() {
+  const form = document.getElementById('login-form');
+  form.addEventListener('submit', function(event) {
+    event.preventDefault();
+    const username = document.getElementById('username').value;
+    const password = document.getElementById('password').value;
+    const statusMessage = document.getElementById('status-message');
+
+    if (username === VALID_USERNAME && password === VALID_PASSWORD) {
+      statusMessage.textContent = 'You are logged in';
+      statusMessage.className = 'success';
+    } else {
+      statusMessage.textContent = 'Invalid username or password';
+      statusMessage.className = 'error';
+    }
+  });
+});
"""


class LocalFrontendTester:
    """Local version of frontend tester that doesn't require GitLab."""

    def __init__(self, workspace_dir: str, llm_config: LLMConfig):
        self.workspace_dir = workspace_dir
        self.llm_config = llm_config
        self.server_process = None
        self.frontend_url = None

    async def run(self):
        """Run the local frontend test."""
        print("=" * 60)
        print("Frontend Tester - Local Test Mode")
        print("=" * 60)

        try:
            # 1. Start the server
            print("\n[1/4] Starting frontend server...")
            self.frontend_url = await self._start_server()
            print(f"      Server running at: {self.frontend_url}")

            # 2. Identify scenarios from mock diff
            print("\n[2/4] Identifying test scenarios from diff...")
            scenarios = await self._identify_scenarios()
            print(f"      Found {len(scenarios)} scenarios:")
            for s in scenarios:
                print(f"        - {s.get('name', 'Unnamed')}")

            # 3. Run scenarios (simplified - just show what would be tested)
            print("\n[3/4] Scenarios to test:")
            for i, scenario in enumerate(scenarios, 1):
                print(f"\n      Scenario {i}: {scenario.get('name', 'Unnamed')}")
                print(f"      Description: {scenario.get('description', 'No description')}")
                if scenario.get('steps'):
                    print("      Steps:")
                    for step in scenario['steps']:
                        print(f"        - {step}")
                if scenario.get('assertions'):
                    print("      Assertions:")
                    for assertion in scenario['assertions']:
                        print(f"        - {assertion}")

            # 4. Summary
            print("\n[4/4] Test Summary")
            print("=" * 60)
            print(f"Frontend URL: {self.frontend_url}")
            print(f"Scenarios identified: {len(scenarios)}")
            print("\nTo manually test:")
            print(f"  1. Open {self.frontend_url} in browser")
            print("  2. Enter username: user")
            print("  3. Enter password: user")
            print("  4. Click Login")
            print("  5. Verify 'You are logged in' appears")
            print("\nPress Ctrl+C to stop the server...")

            # Keep server running for manual testing
            while True:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            print("\n\nStopping server...")
        finally:
            self._cleanup()

    async def _start_server(self) -> str:
        """Start the frontend server."""
        self.server_process = subprocess.Popen(
            ['npx', 'serve', '.', '-l', '3000'],
            cwd=self.workspace_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,
        )

        # Wait for server to start
        await asyncio.sleep(3)
        return 'http://localhost:3000'

    async def _identify_scenarios(self) -> list[dict]:
        """Use LLM to identify test scenarios."""
        prompt = build_scenario_identification_prompt(MOCK_DIFF)

        messages = [
            {'role': 'system', 'content': 'You are a frontend testing expert. Analyze code diffs and identify testable user scenarios. Respond only with valid JSON.'},
            {'role': 'user', 'content': prompt},
        ]

        try:
            response = await acompletion(self.llm_config, messages)

            # Parse JSON from response
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                # Try parsing entire response as JSON
                data = json.loads(response)

            return data.get('scenarios', [])
        except Exception as e:
            print(f"      Warning: Failed to identify scenarios via LLM: {e}")
            # Return default scenarios
            return [
                {
                    'name': 'Successful login',
                    'description': 'User can login with valid credentials',
                    'steps': [
                        'Navigate to login page',
                        'Enter "user" in username field',
                        'Enter "user" in password field',
                        'Click Login button'
                    ],
                    'assertions': [
                        '"You are logged in" message appears'
                    ]
                },
                {
                    'name': 'Failed login',
                    'description': 'User sees error with invalid credentials',
                    'steps': [
                        'Navigate to login page',
                        'Enter "wrong" in username field',
                        'Enter "wrong" in password field',
                        'Click Login button'
                    ],
                    'assertions': [
                        '"Invalid username or password" message appears'
                    ]
                }
            ]

    def _cleanup(self):
        """Stop the server."""
        if self.server_process:
            try:
                os.killpg(os.getpgid(self.server_process.pid), signal.SIGTERM)
                print("Server stopped.")
            except Exception as e:
                print(f"Warning: Failed to stop server: {e}")


def main():
    # Check for API key
    api_key = os.environ.get('LLM_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("Error: Set LLM_API_KEY or ANTHROPIC_API_KEY environment variable")
        print("\nExample:")
        print("  export LLM_API_KEY='your-api-key'")
        print("  python run_local_test.py")
        sys.exit(1)

    # Get workspace directory (test folder)
    workspace_dir = Path(__file__).parent

    # Check for package.json
    if not (workspace_dir / 'package.json').exists():
        print(f"Error: No package.json found in {workspace_dir}")
        sys.exit(1)

    # Create LLM config
    llm_config = LLMConfig.from_env()

    # Run the test
    tester = LocalFrontendTester(str(workspace_dir), llm_config)
    asyncio.run(tester.run())


if __name__ == '__main__':
    main()
