import ast
from pathlib import Path
import unittest


class AppSmokeTest(unittest.TestCase):
    def test_app_parses_and_uses_existing_agent(self):
        source = Path("app.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn('AGENT_NAME = "IT-Helpdesk-Agent"', source)
        self.assertIn("DefaultAzureCredential()", source)
        self.assertIn("FoundryAgent(", source)
        self.assertIn("agent_version=AGENT_VERSION", source)
        self.assertNotIn("create_agent", source)


if __name__ == "__main__":
    unittest.main()
