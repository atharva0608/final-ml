"""
Executor Module - Abstraction layer for infrastructure operations

The Executor provides a clean interface for interacting with infrastructure,
allowing the Decision Engine to be cloud-agnostic and easily testable.

Current Implementation: AWSAgentlessExecutor (uses AWS SDK directly)
Future Options: KubernetesExecutor, AgentBasedExecutor
"""

from .aws_agentless import AWSAgentlessExecutor

__all__ = ['AWSAgentlessExecutor']
