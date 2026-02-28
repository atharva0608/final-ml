"""
Base Agent Class
================

Provides common infrastructure for all agents in the system.
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Standardized agent response format"""
    agent_name: str
    status: str  # SUCCESS, FAILED, PARTIAL
    timestamp: str
    data: Dict[str, Any]
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)


class BaseAgent(ABC):
    """
    Base class for all agents in the system.

    Each agent must implement:
    - system_prompt: The agent's core instructions
    - process: Main execution logic
    - validate_input: Input validation
    - validate_output: Output validation
    """

    def __init__(self, name: str, llm_client=None):
        self.name = name
        self.llm_client = llm_client
        self.logger = logging.getLogger(f"agent.{name}")

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the agent's system prompt"""
        pass

    @abstractmethod
    def process(self, input_data: Dict[str, Any]) -> AgentResponse:
        """
        Main processing logic for the agent.

        Args:
            input_data: Input dictionary conforming to agent's contract

        Returns:
            AgentResponse with results
        """
        pass

    @abstractmethod
    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """
        Validate input data structure.

        Args:
            input_data: Input dictionary to validate

        Returns:
            True if valid, raises ValueError if invalid
        """
        pass

    @abstractmethod
    def validate_output(self, output_data: Dict[str, Any]) -> bool:
        """
        Validate output data structure.

        Args:
            output_data: Output dictionary to validate

        Returns:
            True if valid, raises ValueError if invalid
        """
        pass

    def execute(self, input_data: Dict[str, Any]) -> AgentResponse:
        """
        Execute agent with validation and error handling.

        Args:
            input_data: Input dictionary

        Returns:
            AgentResponse
        """
        try:
            self.logger.info(f"Agent {self.name} starting execution")

            # Validate input
            self.validate_input(input_data)

            # Process
            response = self.process(input_data)

            # Validate output
            self.validate_output(response.data)

            self.logger.info(f"Agent {self.name} completed successfully")
            return response

        except ValueError as e:
            self.logger.error(f"Validation error in {self.name}: {str(e)}")
            return AgentResponse(
                agent_name=self.name,
                status="FAILED",
                timestamp=datetime.utcnow().isoformat(),
                data={},
                error=f"Validation error: {str(e)}"
            )
        except Exception as e:
            self.logger.error(f"Error in {self.name}: {str(e)}", exc_info=True)
            return AgentResponse(
                agent_name=self.name,
                status="FAILED",
                timestamp=datetime.utcnow().isoformat(),
                data={},
                error=str(e)
            )

    def call_llm(self, user_message: str, temperature: float = 0.0) -> str:
        """
        Call LLM with system prompt and user message.

        Args:
            user_message: User message (usually JSON input)
            temperature: Sampling temperature (0.0 for deterministic)

        Returns:
            LLM response string
        """
        if not self.llm_client:
            raise RuntimeError(f"No LLM client configured for {self.name}")

        # This is a placeholder - implement based on your LLM provider
        # Could be OpenAI, Anthropic Claude, local model, etc.
        response = self.llm_client.chat.completions.create(
            model="gpt-4",  # or your model
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=temperature,
            response_format={"type": "json_object"}  # Force JSON output
        )

        return response.choices[0].message.content
