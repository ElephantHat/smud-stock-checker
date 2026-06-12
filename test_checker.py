import os
import json
import unittest
from unittest.mock import patch, MagicMock

# Import the code to test
import checker

class TestStockCheckerState(unittest.TestCase):
    
    def setUp(self):
        # Use a temporary state file for testing
        self.original_state_file = checker.STATE_FILE
        checker.STATE_FILE = os.path.join(checker.SCRIPT_DIR, "state_test.json")
        self.state_changed_file = os.path.join(checker.SCRIPT_DIR, "state_changed.txt")
        self.cleanup()

    def tearDown(self):
        self.cleanup()
        checker.STATE_FILE = self.original_state_file

    def cleanup(self):
        # Remove test artifacts
        for filepath in [checker.STATE_FILE, self.state_changed_file]:
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except OSError:
                    pass

    def get_test_state(self):
        if os.path.exists(checker.STATE_FILE):
            with open(checker.STATE_FILE, 'r') as f:
                return json.load(f)
        return None

    @patch('checker.check_stock_status')
    @patch('checker.send_slack_notification')
    def test_out_of_stock_initially(self, mock_send_slack, mock_check_stock):
        """Test behavior when the item is out of stock and state.json does not exist."""
        mock_check_stock.return_value = False
        
        checker.main()
        
        # Should not try to send Slack notification
        mock_send_slack.assert_not_called()
        # Should not create state_changed.txt because status didn't change (was False, stays False)
        self.assertFalse(os.path.exists(self.state_changed_file))
        # state.json is not created if state didn't change from default (False)
        self.assertIsNone(self.get_test_state())

    @patch('checker.check_stock_status')
    @patch('checker.send_slack_notification')
    def test_transitions_to_in_stock(self, mock_send_slack, mock_check_stock):
        """Test transitioning from out of stock to in stock updates the state and sends a Slack notification."""
        mock_check_stock.return_value = True
        mock_send_slack.return_value = True
        
        # Write initial state: out of stock
        checker.save_state({"last_status": False, "notified": False})
        if os.path.exists(self.state_changed_file):
            os.remove(self.state_changed_file)

        checker.main()

        # Should send Slack notification
        mock_send_slack.assert_called_once()
        self.assertIn("IN STOCK", mock_send_slack.call_args[0][0])
        # State should be updated to in stock (last_status=True, notified=True)
        state = self.get_test_state()
        self.assertTrue(state["notified"])
        self.assertTrue(state["last_status"])
        # Should flag state changed for GitHub Actions
        self.assertTrue(os.path.exists(self.state_changed_file))

    @patch('checker.check_stock_status')
    @patch('checker.send_slack_notification')
    def test_already_in_stock_no_state_change(self, mock_send_slack, mock_check_stock):
        """Test that if the item was already in stock, no state change or notification is sent."""
        mock_check_stock.return_value = True
        
        # Write initial state: already in stock
        checker.save_state({"last_status": True, "notified": True})
        if os.path.exists(self.state_changed_file):
            os.remove(self.state_changed_file)

        checker.main()

        # Should NOT send Slack notification
        mock_send_slack.assert_not_called()
        # State should remain in stock
        state = self.get_test_state()
        self.assertTrue(state["last_status"])
        # Should not flag state change
        self.assertFalse(os.path.exists(self.state_changed_file))

    @patch('checker.check_stock_status')
    @patch('checker.send_slack_notification')
    def test_goes_out_of_stock(self, mock_send_slack, mock_check_stock):
        """Test that going back out of stock resets the state and sends an out-of-stock notification."""
        mock_check_stock.return_value = False
        mock_send_slack.return_value = True
        
        # Write initial state: was in stock
        checker.save_state({"last_status": True, "notified": True})
        if os.path.exists(self.state_changed_file):
            os.remove(self.state_changed_file)

        checker.main()

        # Should send Slack notification
        mock_send_slack.assert_called_once()
        self.assertIn("OUT OF STOCK", mock_send_slack.call_args[0][0])
        # State should be reset to out of stock
        state = self.get_test_state()
        self.assertFalse(state["notified"])
        self.assertFalse(state["last_status"])
        # Should flag state changed
        self.assertTrue(os.path.exists(self.state_changed_file))

if __name__ == "__main__":
    unittest.main()
