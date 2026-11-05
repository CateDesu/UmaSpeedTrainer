"""Save the caller's environment before Qt's runtime hooks change it."""

import os
import sys

sys._uma_launch_environment = os.environ.copy()
