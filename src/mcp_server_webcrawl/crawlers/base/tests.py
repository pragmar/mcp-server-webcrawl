import unittest
import asyncio
import sys

class BaseCrawlerTests(unittest.TestCase):

    def setUp(self):
        # quiet asyncio error on tests, occurring after sucessful completion
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
