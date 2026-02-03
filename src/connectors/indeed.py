from .base import BaseConnector

class IndeedConnector(BaseConnector):
    name = "sg.indeed.com"

    def search(self, query: str, posted_within_days: int = 30):
        # TODO: implement. Start simple with a small number of results.
        return []

