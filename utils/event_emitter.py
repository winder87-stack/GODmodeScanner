"""Event emitter for internal event management."""

from typing import Optional, Dict, List, Callable, Any
import asyncio
from datetime import datetime


class EventEmitter:
    """Event emitter for decoupled event-driven architecture."""

    def __init__(self):
        """Initialize event emitter."""
        self.listeners: Dict[str, List[Callable]] = {}
        self.event_history: List[Dict[str, Any]] = []
        self.max_history = 1000

    def on(self, event_name: str, callback: Callable):
        """Register an event listener.

        Args:
            event_name: Name of the event to listen for
            callback: Callback function (can be async)
        """
        if event_name not in self.listeners:
            self.listeners[event_name] = []

        if callback not in self.listeners[event_name]:
            self.listeners[event_name].append(callback)

    def off(self, event_name: str, callback: Callable):
        """Remove an event listener.

        Args:
            event_name: Event name
            callback: Callback to remove
        """
        if event_name in self.listeners:
            if callback in self.listeners[event_name]:
                self.listeners[event_name].remove(callback)

    async def emit(self, event_name: str, *args, **kwargs):
        """Emit an event to all listeners.

        Args:
            event_name: Event name
            *args: Positional arguments to pass to listeners
            **kwargs: Keyword arguments to pass to listeners
        """
        # Record event in history
        self._record_event(event_name, args, kwargs)

        if event_name not in self.listeners:
            return

        tasks = []
        for callback in self.listeners[event_name]:
            if asyncio.iscoroutinefunction(callback):
                tasks.append(callback(*args, **kwargs))
            else:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    print(f"Error in event listener: {e}")

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def emit_sync(self, event_name: str, *args, **kwargs):
        """Emit an event synchronously (for non-async contexts).

        Args:
            event_name: Event name
            *args: Positional arguments
            **kwargs: Keyword arguments
        """
        self._record_event(event_name, args, kwargs)

        if event_name not in self.listeners:
            return

        for callback in self.listeners[event_name]:
            if not asyncio.iscoroutinefunction(callback):
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    print(f"Error in event listener: {e}")

    def _record_event(self, event_name: str, args: tuple, kwargs: dict):
        """Record event in history.

        Args:
            event_name: Event name
            args: Positional arguments
            kwargs: Keyword arguments
        """
        event_record = {
            'event': event_name,
            'timestamp': datetime.now().isoformat(),
            'args': args,
            'kwargs': kwargs
        }

        self.event_history.append(event_record)

        # Trim history if too large
        if len(self.event_history) > self.max_history:
            self.event_history = self.event_history[-self.max_history:]

    def once(self, event_name: str, callback: Callable):
        """Register a one-time event listener.

        Args:
            event_name: Event name
            callback: Callback function
        """
        async def wrapper(*args, **kwargs):
            self.off(event_name, wrapper)
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)

        self.on(event_name, wrapper)

    def remove_all_listeners(self, event_name: Optional[str] = None):
        """Remove all listeners for an event or all events.

        Args:
            event_name: Optional event name, if None removes all
        """
        if event_name:
            if event_name in self.listeners:
                self.listeners[event_name] = []
        else:
            self.listeners = {}

    def get_event_history(self, event_name: Optional[str] = None, 
                         limit: int = 100) -> List[Dict[str, Any]]:
        """Get event history.

        Args:
            event_name: Optional event name filter
            limit: Maximum number of events to return

        Returns:
            List of event records
        """
        if event_name:
            filtered = [e for e in self.event_history if e['event'] == event_name]
            return filtered[-limit:]
        return self.event_history[-limit:]
