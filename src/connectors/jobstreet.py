from .base import BaseConnector

class JobstreetConnector(BaseConnector):
    name = "sg.jobstreet.com"

    def search(self, query: str, posted_within_days: int = 30):
        # TODO: implement. Start simple with a small number of results.
        return []

