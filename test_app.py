import ast
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from history_store import ConversationStore


class AppSmokeTest(unittest.TestCase):
    def test_app_parses_and_uses_existing_agent(self):
        source = Path("app.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn('AGENT_NAME = "IT-Helpdesk-Agent"', source)
        self.assertIn("DefaultAzureCredential()", source)
        self.assertIn("FoundryAgent(", source)
        self.assertIn("agent_version=AGENT_VERSION", source)
        self.assertIn("prompt_with_saved_context", source)
        self.assertIn("Continue the following IT helpdesk conversation", source)
        self.assertIn("local_troubleshooting_response", source)
        self.assertIn("IT support ready", source)
        self.assertNotIn('st.error(f"Could not reach the helpdesk agent: {error}")', source)
        self.assertNotIn("create_agent", source)

    def test_conversations_survive_reopening_and_preserve_message_order(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "history.db"
            first_store = ConversationStore(database)
            first = first_store.create_conversation()
            second = first_store.create_conversation()
            first_store.append_message(first, "user", "Wi-Fi is unavailable")
            first_store.append_message(first, "assistant", "Check airplane mode first.")
            first_store.append_message(second, "user", "VPN is disconnected")

            reopened_store = ConversationStore(database)
            self.assertEqual(
                [message["content"] for message in reopened_store.load_messages(first)],
                ["Wi-Fi is unavailable", "Check airplane mode first."],
            )
            self.assertEqual(len(reopened_store.list_conversations()), 2)
            self.assertEqual(reopened_store.load_messages(second)[0]["content"], "VPN is disconnected")


if __name__ == "__main__":
    unittest.main()
