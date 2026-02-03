class BaseConnector:
    name = "Base"

    def search(self, query: str, posted_within_days: int = 30):
        """
        Return a list of dict rows matching REQUIRED_COLS (some may be Unverified).
        Each row should contain:
          Job title available, employer, job post url link, job post from what source,
          date job post was posted, application closing date, key job requirement,
          estimated salary, job full-time or part-time
        """
        raise NotImplementedError

