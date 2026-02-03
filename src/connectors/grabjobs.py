from .base import BaseConnector

class GrabjobsConnector(BaseConnector):
    name = "Grabjobs.co/singapore"

    def search(self, query: str, posted_within_days: int = 30):
        # TODO: implement. Start simple with a small number of results.
        return []

