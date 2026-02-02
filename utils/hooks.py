"""Webhook system for event notifications and integrations."""

from typing import Dict, List, Optional, Any, Callable
import asyncio
import aiohttp
from datetime import datetime
import json


class Hooks:
    """Manages webhooks for event notifications."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize hooks system.

        Args:
            config: Webhook configuration
        """
        self.config = config or {
            'retry_attempts': 3,
            'retry_delay': 5,
            'timeout': 30
        }

        self.registered_hooks: Dict[str, List[str]] = {}
        self.handlers: Dict[str, Callable] = {}
        self.session: Optional[aiohttp.ClientSession] = None

    def register_webhook(self, event_type: str, url: str):
        """Register a webhook URL for an event type.

        Args:
            event_type: Type of event to subscribe to
            url: Webhook URL
        """
        if event_type not in self.registered_hooks:
            self.registered_hooks[event_type] = []

        if url not in self.registered_hooks[event_type]:
            self.registered_hooks[event_type].append(url)

    def register_handler(self, event_type: str, handler: Callable):
        """Register a handler function for an event type.

        Args:
            event_type: Type of event
            handler: Async handler function
        """
        self.handlers[event_type] = handler

    async def trigger(self, event_type: str, data: Dict[str, Any]):
        """Trigger an event and notify all registered webhooks.

        Args:
            event_type: Type of event
            data: Event data
        """
        # Call registered handler if exists
        if event_type in self.handlers:
            await self.handlers[event_type](data)

        # Notify webhooks
        if event_type in self.registered_hooks:
            tasks = []
            for url in self.registered_hooks[event_type]:
                tasks.append(self._send_webhook(url, event_type, data))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_webhook(self, url: str, event_type: str, data: Dict[str, Any]):
        """Send webhook notification.

        Args:
            url: Webhook URL
            event_type: Event type
            data: Event data
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        payload = {
            'event_type': event_type,
            'timestamp': datetime.now().isoformat(),
            'data': data
        }

        for attempt in range(self.config['retry_attempts']):
            try:
                async with self.session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.config['timeout'])
                ) as response:
                    if response.status < 400:
                        return
            except Exception as e:
                if attempt == self.config['retry_attempts'] - 1:
                    print(f"Webhook failed after {attempt + 1} attempts: {e}")
                else:
                    await asyncio.sleep(self.config['retry_delay'])

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
