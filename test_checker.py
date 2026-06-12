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
    @patch('checker.send_email_notification')
    def test_out_of_stock_initially(self, mock_send_email, mock_check_stock):
        """Test behavior when the item is out of stock and state.json does not exist."""
        mock_check_stock.return_value = False
        
        checker.main()
        
        # Should not try to send email
        mock_send_email.assert_not_called()
        # Should not create state_changed.txt because status didn't change (was False, stays False)
        self.assertFalse(os.path.exists(self.state_changed_file))
        # state.json is not created if state didn't change from default (False)
        self.assertIsNone(self.get_test_state())

    @patch('checker.check_stock_status')
    @patch('checker.send_email_notification')
    def test_transitions_to_in_stock_and_emails(self, mock_send_email, mock_check_stock):
        """Test transitioning from out of stock to in stock."""
        mock_check_stock.return_value = True
        mock_send_email.return_value = True
        
        # Write initial state: out of stock, not notified
        checker.save_state({"last_status": False, "notified": False})
        if os.path.exists(self.state_changed_file):
            os.remove(self.state_changed_file)

        checker.main()

        # Should send email
        mock_send_email.assert_called_once()
        # State should be updated to notified: true
        state = self.get_test_state()
        self.assertTrue(state["notified"])
        self.assertTrue(state["last_status"])
        # Should flag state changed for GitHub Actions
        self.assertTrue(os.path.exists(self.state_changed_file))

    @patch('checker.check_stock_status')
    @patch('checker.send_email_notification')
    def test_already_in_stock_no_second_email(self, mock_send_email, mock_check_stock):
        """Test that if the item is in stock but we already notified, we don't spam emails."""
        mock_check_stock.return_value = True
        
        # Write initial state: already notified
        checker.save_state({"last_status": True, "notified": True})
        if os.path.exists(self.state_changed_file):
            os.remove(self.state_changed_file)

        checker.main()

        # Should NOT send email
        mock_send_email.assert_not_called()
        # State should remain notified: true
        state = self.get_test_state()
        self.assertTrue(state["notified"])
        # Should not flag state change
        self.assertFalse(os.path.exists(self.state_changed_file))

    @patch('checker.check_stock_status')
    @patch('checker.send_email_notification')
    def test_goes_out_of_stock_resets_notified(self, mock_send_email, mock_check_stock):
        """Test that going back out of stock resets the notified flag."""
        mock_check_stock.return_value = False
        
        # Write initial state: was in stock and notified
        checker.save_state({"last_status": True, "notified": True})
        if os.path.exists(self.state_changed_file):
            os.remove(self.state_changed_file)

        checker.main()

        # Should NOT send email
        mock_send_email.assert_not_called()
        # State should be reset to notified: false, last_status: false
        state = self.get_test_state()
        self.assertFalse(state["notified"])
        self.assertFalse(state["last_status"])
        # Should flag state changed
        self.assertTrue(os.path.exists(self.state_changed_file))

if __name__ == "__main__":
    unittest.main()
