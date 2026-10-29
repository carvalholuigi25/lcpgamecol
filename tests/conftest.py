"""Test-only accounts.

The app has no built-in admin password, so the suite configures one here before
any test module imports the app. These credentials exist only in tests.
"""

import os

os.environ.pop("AUTH_USERS", None)
os.environ["AUTH_USERNAME"] = "admin"
os.environ["AUTH_PASSWORD"] = "1234"
