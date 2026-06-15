from abc import ABC, abstractmethod
from stake_watch.models.alert import Alert

class BaseNotifier(ABC):
    @abstractmethod
    async def send(self, alert: Alert) -> bool: ...
