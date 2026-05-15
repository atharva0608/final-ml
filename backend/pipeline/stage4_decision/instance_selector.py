"""
Instance Selector -- pipeline stage re-export shim
Source of truth: backend.services.instance_selector
Do NOT add implementation here -- edit the service module instead.
"""
# flake8: noqa: F401, F403
from backend.services.instance_selector import *  # noqa
from backend.services.instance_selector import TransientError, PermanentError, DensityTransientError
