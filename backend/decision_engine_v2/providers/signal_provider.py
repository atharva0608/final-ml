"""
AWS Signal Providers

Checks for AWS interrupt signals (Rebalance/Termination notices).
"""

import requests
from ..context import SignalType
from ..interfaces import ISignalProvider


class MockSignalProvider(ISignalProvider):
    """Mock signal provider for testing"""

    def __init__(self, mock_signal: SignalType = SignalType.NONE):
        self.mock_signal = mock_signal

    def check_signals(self, instance_id: str = None) -> SignalType:
        """Return mock signal"""
        return self.mock_signal


class IMDSSignalProvider(ISignalProvider):
    """
    Real signal provider using AWS Instance Metadata Service (IMDS)

    Checks:
    - http://169.254.169.254/latest/meta-data/events/recommendations/rebalance
    - http://169.254.169.254/latest/meta-data/spot/instance-action
    """

    IMDS_BASE_URL = "http://169.254.169.254/latest/meta-data"
    TOKEN_URL = "http://169.254.169.254/latest/api/token"

    def __init__(self, timeout: float = 0.5):
        self.timeout = timeout

    def check_signals(self, instance_id: str = None) -> SignalType:
        """Check IMDS for interrupt signals"""
        try:
            # Get IMDSv2 token
            token = self._get_token()

            # Check for termination notice first (highest priority)
            if self._check_termination(token):
                return SignalType.TERMINATION

            # Check for rebalance recommendation
            if self._check_rebalance(token):
                return SignalType.REBALANCE

            return SignalType.NONE

        except Exception as e:
            # IMDS not available (not running on EC2) or network error
            # Return NONE and let the system continue
            return SignalType.NONE

    def _get_token(self) -> str:
        """Get IMDSv2 token"""
        headers = {"X-aws-ec2-metadata-token-ttl-seconds": "21600"}
        response = requests.put(
            self.TOKEN_URL,
            headers=headers,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.text

    def _check_termination(self, token: str) -> bool:
        """Check for spot termination notice"""
        headers = {"X-aws-ec2-metadata-token": token}
        url = f"{self.IMDS_BASE_URL}/spot/instance-action"

        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            if response.status_code == 200:
                # Termination notice exists
                return True
        except:
            pass

        return False

    def _check_rebalance(self, token: str) -> bool:
        """Check for rebalance recommendation"""
        headers = {"X-aws-ec2-metadata-token": token}
        url = f"{self.IMDS_BASE_URL}/events/recommendations/rebalance"

        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            if response.status_code == 200:
                # Rebalance recommendation exists
                return True
        except:
            pass

        return False
