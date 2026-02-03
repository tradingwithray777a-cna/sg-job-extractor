from .base import BaseConnector

class LinkedinConnector(BaseConnector):
    name = "linkedin.com/jobs/jobs-in-singapore"

    def search(self, query: str, posted_within_days: int = 30):
        # TODO: implement. Start simple with a small number of results.
        return []

