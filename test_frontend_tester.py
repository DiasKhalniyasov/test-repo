#!/usr/bin/env python3
"""
Local test runner for frontend_tester agent.

Runs the actual FrontendTester agent against the local test app without GitLab.
Simulates an MR with a description/diff and tests the full agent workflow.

Usage:
    cd agents
    python test/test_frontend_tester.py

    # With custom description:
    python test/test_frontend_tester.py --description "Test the login form with user/pass credentials"

    # Dry run (don't generate test files):
    python test/test_frontend_tester.py --dry-run

Requirements:
    - Set LLM_API_KEY or ANTHROPIC_API_KEY environment variable
    - npm/npx available for serving the test app
"""

import os
import sys
import json
import asyncio
import subprocess
import signal
import argparse
import logging
import re
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
agents_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(agents_dir))

from core.config import LLMConfig
from core.llm import acompletion, completion_with_tools
from core.models import FrontendTestOutcome
from prompts.frontend_tester import (
    FRONTEND_TESTER_SYSTEM_PROMPT,
    build_scenario_identification_prompt,
    build_test_execution_prompt,
    format_test_results,
)
from frontend_tester import PLAYWRIGHT_MCP_TOOLS

# Configure logging (WARNING by default, INFO with -v)
logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Silence noisy loggers
logging.getLogger('litellm').setLevel(logging.ERROR)
logging.getLogger('httpx').setLevel(logging.ERROR)
logging.getLogger('httpcore').setLevel(logging.ERROR)
logging.getLogger('mcp').setLevel(logging.ERROR)
logging.getLogger('LiteLLM').setLevel(logging.ERROR)

# Disable litellm debug mode
import litellm
litellm.set_verbose = False
litellm._logging._disable_debugging()


# =============================================================================
# Test App Description (simulates MR diff/description)
# =============================================================================

DEFAULT_DESCRIPTION = """
## Login Page Implementation

This MR adds a simple login page with the following features:

### Features:
- Username and password input fields
- Login button to submit credentials
- Status message display area
- Form validation

### Valid Credentials:
- Username: `user`
- Password: `user`

### Expected Behavior:
1. **Successful Login**: Enter "user" / "user" → Shows "You are logged in" message
2. **Failed Login**: Enter wrong credentials → Shows "Invalid username or password" message

### Files Changed:
- `index.html` - Login form structure
- `app.js` - Form submission handler and validation
- `style.css` - Basic styling
"""

# Simulated diff from the test app files
TEST_APP_DIFF = """diff --git a/index.html b/index.html
new file mode 100644
--- /dev/null
+++ b/index.html
@@ -0,0 +1,25 @@
+<!DOCTYPE html>
+<html lang="en">
+<head>
+  <meta charset="UTF-8">
+  <meta name="viewport" content="width=device-width, initial-scale=1.0">
+  <title>Login Page</title>
+  <link rel="stylesheet" href="style.css">
+</head>
+<body>
+  <div class="login-container">
+    <h1>Login</h1>
+    <form id="login-form">
+      <div class="form-group">
+        <input type="text" id="username" placeholder="Enter username" required>
+      </div>
+      <div class="form-group">
+        <input type="password" id="password" placeholder="Enter password" required>
+      </div>
+      <button type="submit" id="login-button">Login</button>
+    </form>
+    <div id="status-message"></div>
+  </div>
+  <script src="app.js"></script>
+</body>
+</html>

diff --git a/app.js b/app.js
new file mode 100644
--- /dev/null
+++ b/app.js
@@ -0,0 +1,22 @@
+// Valid credentials
+const VALID_USERNAME = 'user';
+const VALID_PASSWORD = 'user';
+
+document.addEventListener('DOMContentLoaded', function() {
+  const form = document.getElementById('login-form');
+  const statusMessage = document.getElementById('status-message');
+
+  form.addEventListener('submit', function(event) {
+    event.preventDefault();
+
+    const username = document.getElementById('username').value;
+    const password = document.getElementById('password').value;
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


# =============================================================================
# Local Frontend Tester (No GitLab Dependency)
# =============================================================================

class LocalFrontendTester:
    """
    Frontend E2E Tester that runs locally without GitLab.

    This class replicates the core functionality of FrontendTester
    but uses local description/diff instead of fetching from GitLab MR.
    """

    def __init__(
        self,
        workspace_dir: str,
        llm_config: LLMConfig,
        description: str = DEFAULT_DESCRIPTION,
        diff: str = TEST_APP_DIFF,
        max_iterations: int = 15,
        dry_run: bool = False,
        output_dir: Optional[str] = None,
    ):
        """
        Initialize the local frontend tester.

        Args:
            workspace_dir: Directory containing the test app
            llm_config: LLM configuration
            description: MR description (what the code does)
            diff: Code diff to analyze
            max_iterations: Maximum iterations per scenario
            dry_run: If True, don't generate test files
            output_dir: Directory to save generated tests (default: workspace_dir/e2e)
        """
        self.workspace_dir = workspace_dir
        self.llm_config = llm_config
        self.description = description
        self.diff = diff
        self.max_iterations = max_iterations
        self.dry_run = dry_run
        self.output_dir = output_dir or os.path.join(workspace_dir, 'e2e', 'generated')

        self.server_process: Optional[subprocess.Popen] = None
        self.frontend_url: Optional[str] = None
        self.mcp_process: Optional[subprocess.Popen] = None


    async def test(self) -> FrontendTestOutcome:
        """
        Execute the frontend testing process.

        Returns:
            The test outcome
        """
        print("\n" + "=" * 60)
        print("🧪 Frontend Tester - Local Mode")
        print("=" * 60)

        try:
            # 1. Identify test scenarios from diff/description
            print("\n[1/5] 📝 Identifying test scenarios...")
            scenarios = await self._identify_scenarios()

            if not scenarios:
                print("⚠️  No test scenarios identified")
                return FrontendTestOutcome.SKIPPED

            print(f"✅ Found {len(scenarios)} scenarios:")
            for i, s in enumerate(scenarios, 1):
                print(f"   {i}. {s.get('name', 'Unnamed')}")

            # 2. Start frontend server
            print("\n[2/5] 🚀 Starting frontend server...")
            self.frontend_url = await self._start_server()
            print(f"✅ Server running at: {self.frontend_url}")

            # 3. Start Playwright MCP server (optional - for real browser testing)
            print("\n[3/5] 🎭 Starting Playwright MCP server...")
            await self._start_mcp_server()
            print("✅ MCP server ready")

            # 4. Run scenarios
            print("\n[4/5] 🔄 Running test scenarios...")
            results = await self._run_scenarios(scenarios)

            # 5. Process results
            print("\n[5/5] 📊 Processing results...")
            passed = [r for r in results if r.get('status') == 'passed']
            failed = [r for r in results if r.get('status') == 'failed']

            # Generate summary
            summary = self._generate_summary(passed, failed)

            # Display results
            self._display_results(results, summary)

            # Save test files
            if passed and not self.dry_run:
                self._save_test_files(passed)

            # Determine outcome
            if not failed:
                return FrontendTestOutcome.ALL_PASSED
            elif not passed:
                return FrontendTestOutcome.ALL_FAILED
            else:
                return FrontendTestOutcome.SOME_FAILED

        except Exception as e:
            logger.error(f'Frontend test error: {e}')
            print(f"\n❌ Error: {e}")
            return FrontendTestOutcome.ERROR

        finally:
            self._cleanup()

    async def _identify_scenarios(self) -> list[dict]:
        """Use LLM to identify exactly ONE test scenario from description."""
        prompt = f"""Based on this test description, create exactly ONE test scenario.

Description:
{self.description}

Respond with JSON containing exactly one scenario:
```json
{{
  "scenarios": [
    {{
      "name": "short scenario name",
      "description": "what this tests",
      "steps": ["step 1", "step 2", ...],
      "assertions": ["expected result 1", ...]
    }}
  ]
}}
```

IMPORTANT: Return exactly ONE scenario, not multiple."""

        messages = [
            {
                'role': 'system',
                'content': 'You are a frontend testing expert. Create exactly ONE test scenario from the description. Respond only with valid JSON.'
            },
            {'role': 'user', 'content': prompt},
        ]

        try:
            response = await acompletion(self.llm_config, messages)

            # Parse JSON from response
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(response)

            scenarios = data.get('scenarios', [])
            # Ensure only 1 scenario
            return scenarios[:1] if scenarios else self._get_default_scenarios()

        except Exception as e:
            logger.error(f'Failed to identify scenarios: {e}')
            return self._get_default_scenarios()

    def _get_default_scenarios(self) -> list[dict]:
        """Return single default test scenario."""
        return [
            {
                'name': 'Successful login with valid credentials',
                'description': 'User can login with username "user" and password "user"',
                'steps': [
                    'Navigate to the login page',
                    'Enter "user" in the username field',
                    'Enter "user" in the password field',
                    'Click the Login button',
                ],
                'assertions': [
                    '"You are logged in" message should appear',
                ],
            },
        ]

    async def _start_server(self, timeout: int = 30) -> str:
        """Start the frontend server and detect its URL."""
        # Check for package.json to determine start command
        package_json_path = Path(self.workspace_dir) / 'package.json'

        if package_json_path.exists():
            with open(package_json_path) as f:
                pkg = json.load(f)

            scripts = pkg.get('scripts', {})

            # Determine start command
            if 'dev' in scripts:
                start_cmd = 'npm run dev'
            elif 'start' in scripts:
                start_cmd = 'npm start'
            elif 'serve' in scripts:
                start_cmd = 'npm run serve'
            else:
                # Fallback to serve static files
                start_cmd = 'npx serve . -l 3001'
        else:
            # No package.json, use static file server
            start_cmd = 'npx serve . -l 3001'


        self.server_process = subprocess.Popen(
            start_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=self.workspace_dir,
            preexec_fn=os.setsid,
        )

        # URL patterns to detect
        url_patterns = [
            r'(https?://localhost:\d+)',
            r'(https?://127\.0\.0\.1:\d+)',
            r'Local:\s*(https?://[^\s]+)',
            r'listening.*?on\s*(https?://[^\s]+)',
            r'localhost:(\d+)',
        ]

        start_time = asyncio.get_event_loop().time()

        while True:
            if asyncio.get_event_loop().time() - start_time > timeout:
                logger.warning('Server start timeout, using default port')
                return 'http://localhost:3001'

            line = self.server_process.stdout.readline()
            if not line:
                await asyncio.sleep(0.1)
                continue

            line_str = line.decode('utf-8', errors='ignore')

            for pattern in url_patterns:
                match = re.search(pattern, line_str, re.IGNORECASE)
                if match:
                    url = match.group(1)
                    if not url.startswith('http'):
                        url = f'http://localhost:{url}'
                    await asyncio.sleep(2)  # Let server fully initialize
                    return url

    async def _start_mcp_server(self):
        """Start the Playwright MCP server using mcp library."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        try:
            server_params = StdioServerParameters(
                command='npx',
                args=['@playwright/mcp@latest'],
            )

            # Create client connection
            self._mcp_stdio = stdio_client(server_params)
            self._mcp_read, self._mcp_write = await self._mcp_stdio.__aenter__()

            # Create session
            self._mcp_session = ClientSession(self._mcp_read, self._mcp_write)
            await self._mcp_session.__aenter__()

            # Initialize
            await self._mcp_session.initialize()

        except Exception as e:
            logger.error(f'MCP start failed: {e}')
            raise

    async def _mcp_call_tool(self, name: str, arguments: dict) -> dict:
        """Call an MCP tool."""
        result = await self._mcp_session.call_tool(name, arguments)
        # Extract text content
        if result.content:
            for item in result.content:
                if hasattr(item, 'text'):
                    return {'result': item.text}
        return {'result': str(result)}

    async def _run_scenarios(self, scenarios: list[dict]) -> list[dict]:
        """Run all test scenarios."""
        results = []
        total_iterations = 0

        for i, scenario in enumerate(scenarios, 1):
            if total_iterations >= self.max_iterations:
                logger.warning(f'Max iterations ({self.max_iterations}) reached')
                break

            print(f"\n   Running scenario {i}/{len(scenarios)}: {scenario.get('name', 'Unnamed')}")

            result = await self._run_single_scenario(scenario)
            results.append(result)

            status_icon = "✅" if result.get('status') == 'passed' else "❌"
            print(f"   {status_icon} {result.get('status', 'unknown')}")

            total_iterations += result.get('iterations_used', 1)

        return results

    async def _run_single_scenario(self, scenario: dict) -> dict:
        """Run a single test scenario using LLM with browser tools."""
        prompt = build_test_execution_prompt(scenario, self.frontend_url)

        messages = [
            {'role': 'system', 'content': FRONTEND_TESTER_SYSTEM_PROMPT},
            {'role': 'user', 'content': prompt},
        ]

        iterations = 0
        max_scenario_iterations = min(10, self.max_iterations)

        while iterations < max_scenario_iterations:
            iterations += 1

            try:
                response = await completion_with_tools(
                    self.llm_config,
                    messages,
                    PLAYWRIGHT_MCP_TOOLS,
                )

                # Check for finish_scenario tool call
                tool_calls = response.get('tool_calls', [])

                for tool_call in tool_calls:
                    func_name = tool_call.get('function', {}).get('name')

                    if func_name == 'finish_scenario':
                        args = json.loads(tool_call.get('function', {}).get('arguments', '{}'))
                        return {
                            'name': scenario.get('name', 'Unnamed'),
                            'status': args.get('status', 'failed'),
                            'explanation': args.get('explanation', ''),
                            'test_code': args.get('test_code', ''),
                            'iterations_used': iterations,
                        }

                # Execute other tool calls and continue
                if tool_calls:
                    tool_results = await self._execute_tools(tool_calls)
                    messages.append({
                        'role': 'assistant',
                        'content': response.get('content', ''),
                        'tool_calls': tool_calls
                    })
                    for result in tool_results:
                        messages.append({
                            'role': 'tool',
                            'tool_call_id': result['id'],
                            'content': result['content']
                        })
                else:
                    break

            except Exception as e:
                logger.error(f'Error in scenario execution: {e}')
                return {
                    'name': scenario.get('name', 'Unnamed'),
                    'status': 'failed',
                    'explanation': f'Execution error: {str(e)}',
                    'iterations_used': iterations,
                }

        return {
            'name': scenario.get('name', 'Unnamed'),
            'status': 'failed',
            'explanation': 'Max iterations reached without completing scenario',
            'iterations_used': iterations,
        }

    async def _execute_tools(self, tool_calls: list) -> list[dict]:
        """Execute browser tool calls via MCP server."""
        results = []

        for tool_call in tool_calls:
            func_name = tool_call.get('function', {}).get('name')
            func_args = json.loads(tool_call.get('function', {}).get('arguments', '{}'))
            tool_id = tool_call.get('id', '')

            print(f"      → {func_name}")

            try:
                result = await self._mcp_call_tool(func_name, func_args)
                result_str = json.dumps(result)

                # Truncate large results
                if len(result_str) > 2000:
                    result_str = result_str[:2000] + '...[truncated]'

                results.append({'id': tool_id, 'content': result_str})

            except Exception as e:
                print(f"      ⚠ {func_name} error: {e}")
                results.append({'id': tool_id, 'content': f'{{"error": "{e}"}}'})

        return results

    def _generate_summary(self, passed: list, failed: list) -> str:
        """Generate a summary of test results."""
        total = len(passed) + len(failed)

        if not failed:
            return f'All {total} scenarios passed successfully. E2E tests have been generated.'
        elif not passed:
            return f'All {total} scenarios failed. Please review the explanations above.'
        else:
            return f'{len(passed)} of {total} scenarios passed. Tests generated for passing scenarios.'

    def _display_results(self, results: list, summary: str):
        """Display test results in the terminal."""
        print("\n" + "=" * 60)
        print("📊 Test Results")
        print("=" * 60)

        passed = [r for r in results if r.get('status') == 'passed']
        failed = [r for r in results if r.get('status') == 'failed']

        print(f"\nTotal: {len(results)} scenarios")
        print(f"✅ Passed: {len(passed)}")
        print(f"❌ Failed: {len(failed)}")

        if passed:
            print("\n--- Passed Scenarios ---")
            for r in passed:
                print(f"  ✅ {r.get('name', 'Unnamed')}")

        if failed:
            print("\n--- Failed Scenarios ---")
            for r in failed:
                print(f"  ❌ {r.get('name', 'Unnamed')}")
                if r.get('explanation'):
                    print(f"     Reason: {r.get('explanation')}")

        print(f"\n📝 Summary: {summary}")

        # Show formatted comment (as it would appear in GitLab)
        print("\n" + "-" * 60)
        print("Comment Preview (as it would appear in MR):")
        print("-" * 60)
        comment = format_test_results(results, summary)
        print(comment)

    def _save_test_files(self, passed_scenarios: list):
        """Save generated test files to output directory."""
        os.makedirs(self.output_dir, exist_ok=True)

        print(f"\n💾 Saving test files to: {self.output_dir}")

        for scenario in passed_scenarios:
            if not scenario.get('test_code'):
                continue

            # Generate filename from scenario name
            name = scenario.get('name', 'test').lower()
            name = re.sub(r'[^a-z0-9]+', '-', name).strip('-')
            filename = f'{name}.spec.ts'
            filepath = os.path.join(self.output_dir, filename)

            with open(filepath, 'w') as f:
                f.write(scenario['test_code'])

            print(f"   📄 {filename}")

    async def _cleanup_async(self):
        """Async cleanup for MCP session."""
        if hasattr(self, '_mcp_session'):
            try:
                await self._mcp_session.__aexit__(None, None, None)
            except Exception:
                pass
        if hasattr(self, '_mcp_stdio'):
            try:
                await self._mcp_stdio.__aexit__(None, None, None)
            except Exception:
                pass

    def _cleanup(self):
        """Clean up server processes."""
        print("\n🧹 Cleaning up...")

        # Cleanup MCP session
        try:
            asyncio.get_event_loop().run_until_complete(self._cleanup_async())
        except Exception:
            pass

        if self.server_process:
            try:
                os.killpg(os.getpgid(self.server_process.pid), signal.SIGTERM)
            except Exception:
                pass


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Run frontend tester agent locally without GitLab',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_frontend_tester.py
  python test_frontend_tester.py --dry-run
  python test_frontend_tester.py --description "Test login with admin/admin"
  python test_frontend_tester.py --max-iterations 20
        """
    )

    parser.add_argument(
        '--description', '-d',
        type=str,
        default=DEFAULT_DESCRIPTION,
        help='MR description (what the code does)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without generating test files'
    )

    parser.add_argument(
        '--max-iterations', '-m',
        type=int,
        default=15,
        help='Maximum iterations per scenario (default: 15)'
    )

    parser.add_argument(
        '--output-dir', '-o',
        type=str,
        help='Directory to save generated tests'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Check for API key
    api_key = os.environ.get('LLM_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("❌ Error: Set LLM_API_KEY or ANTHROPIC_API_KEY environment variable")
        print("\nExample:")
        print("  export LLM_API_KEY='your-api-key'")
        print("  python test_frontend_tester.py")
        sys.exit(1)

    # Get workspace directory (test folder with the app)
    workspace_dir = Path(__file__).parent

    # Check for required files
    if not (workspace_dir / 'index.html').exists():
        print(f"❌ Error: No index.html found in {workspace_dir}")
        print("Make sure you're running from the agents directory")
        sys.exit(1)

    # Create LLM config
    llm_config = LLMConfig.from_env()

    # Create and run the tester
    tester = LocalFrontendTester(
        workspace_dir=str(workspace_dir),
        llm_config=llm_config,
        description=args.description,
        diff=TEST_APP_DIFF,
        max_iterations=args.max_iterations,
        dry_run=args.dry_run,
        output_dir=args.output_dir,
    )

    # Run the test
    outcome = asyncio.run(tester.test())

    print("\n" + "=" * 60)
    print(f"🏁 Final Outcome: {outcome.value}")
    print("=" * 60)

    # Exit with appropriate code
    if outcome == FrontendTestOutcome.ALL_PASSED:
        sys.exit(0)
    elif outcome == FrontendTestOutcome.SKIPPED:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
