from .base import BaseConnector

class MyCareersFutureConnector(BaseConnector):
    name = "mycareersfuture.gov.sg"

    def search(self, query: str, posted_within_days: int = 30):
        # MCF often requires JS rendering and may block bots.
        # For MVP, return empty and let Notes explain access constraints.
        return []

