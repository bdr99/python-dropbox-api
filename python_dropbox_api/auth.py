from abc import ABC, abstractmethod
import logging

from aiohttp import ClientSession


class Auth(ABC):
    """Class to get a valid access token."""

    def __init__(self, websession: ClientSession) -> None:
        """Initialize the auth."""
        self._logger = logging.getLogger(__name__)
        self.websession = websession

    @abstractmethod
    async def async_get_access_token(self) -> str:
        """Return a valid access token."""
