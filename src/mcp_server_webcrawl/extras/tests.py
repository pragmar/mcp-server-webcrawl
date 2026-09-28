import io
import os
import tempfile
import threading
import time
import unittest

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final
from unittest.mock import patch

from PIL import Image

import mcp_server_webcrawl.extras.thumbnails as thumbnails
from mcp_server_webcrawl.extras.thumbnails import ThumbnailManager

# under the 2s GET timeout, so only the deadline can stop a slow fetch
# margin to accomodate cancellation, session close, thread handoff, etc.
SLOW_RESPONSE_SECONDS: Final[float] = 1.8
TEST_TIMEOUT_SECONDS: Final[float] = 1.0
TEST_TIMEOUT_MARGIN_SECONDS: Final[float] = 0.5


class ImageRequestHandler(BaseHTTPRequestHandler):
    """
    /fast/*.png answers at once, /slow/*.png answers HEAD at once and GET late.
    """
    png_bytes: bytes = b""

    def do_HEAD(self):
        self.__send_headers()

    def do_GET(self):
        if self.path.startswith("/slow/"):
            time.sleep(SLOW_RESPONSE_SECONDS)
        try:
            self.__send_headers()
            self.wfile.write(self.png_bytes)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # the client gave up at its deadline, as intended

    def __send_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(self.png_bytes)))
        self.end_headers()

    def log_message(self, format, *args):
        pass


class ThumbnailDeadlineTests(unittest.TestCase):
    """
    A thumbnails request waits no longer than its deadline, and returns whatever
    finished by then, rather than waiting out every fetch and returning nothing.
    """

    def setUp(self):
        image_buffer = io.BytesIO()
        Image.new("RGB", (32, 32), (200, 40, 40)).save(image_buffer, format="PNG")
        ImageRequestHandler.png_bytes = image_buffer.getvalue()

        self.__server = ThreadingHTTPServer(("127.0.0.1", 0), ImageRequestHandler)
        self.__server.daemon_threads = True
        threading.Thread(target=self.__server.serve_forever, daemon=True).start()
        self.addCleanup(self.__server.server_close)
        self.addCleanup(self.__server.shutdown)
        self.base_url: str = f"http://127.0.0.1:{self.__server.server_address[1]}"

        # thumbnails cache to disk by url, keep them out of the real data directory
        temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temp_directory.cleanup)
        for patcher in (
            patch.object(thumbnails, "DATA_DIRECTORY", Path(temp_directory.name)),
            patch.object(thumbnails, "THUMBNAIL_TIMEOUT_SECONDS", TEST_TIMEOUT_SECONDS),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def __urls(self, speed: str, count: int) -> list[str]:
        return [f"{self.base_url}/{speed}/image{i}.png" for i in range(count)]

    def __get_thumbnails(self, urls: list[str]) -> tuple[dict[str, str | None], float]:
        started: float = time.monotonic()
        results: dict[str, str | None] = ThumbnailManager().get_thumbnails(urls)
        return results, time.monotonic() - started

    def test_all_fast_complete(self):
        """
        Baseline, nothing near timeout, everything returned.
        """
        urls: list[str] = self.__urls("fast", 4)
        results, _ = self.__get_thumbnails(urls)
        self.assertTrue(all(results[url] is not None for url in urls))

    def test_timeout_returns_partial(self):
        """
        Past the deadline, finished thumbnails are returned and the stragglers are
        None, at the deadline, not after the slowest fetch.
        """
        fast_urls: list[str] = self.__urls("fast", 4)
        slow_urls: list[str] = self.__urls("slow", 2)
        results, elapsed = self.__get_thumbnails(fast_urls + slow_urls)

        self.assertLess(elapsed, TEST_TIMEOUT_SECONDS + TEST_TIMEOUT_MARGIN_SECONDS,
                f"waited {elapsed:.2f}s, past the {TEST_TIMEOUT_SECONDS}s timeout")
        self.assertTrue(all(results[url] is not None for url in fast_urls), "finished thumbnails discarded")
        self.assertTrue(all(results[url] is None for url in slow_urls))

    def test_slow_fetch_does_not_block_others(self):
        """
        A slow fetch holds its own slot only. Batched, it held its whole batch, and the
        next batch never started before the deadline.
        """
        slow_urls: list[str] = self.__urls("slow", 1)
        fast_urls: list[str] = self.__urls("fast", thumbnails.HTTP_THREADS * 2 - 1)
        results, _ = self.__get_thumbnails(slow_urls + fast_urls)

        missing: list[str] = [url for url in fast_urls if results[url] is None]
        self.assertEqual(missing, [], "fast thumbnails queued behind a slow one")
        self.assertIsNone(results[slow_urls[0]])


class ThumbnailCacheCleanupTests(unittest.TestCase):
    """
    Cleanup removes stale cached thumbnails ({md5}.webp, past 4 hours), and only those.
    The pattern once lacked the extension, matched nothing, and the cache grew forever.
    """

    def setUp(self):
        temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temp_directory.cleanup)
        patcher = patch.object(thumbnails, "DATA_DIRECTORY", Path(temp_directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.manager: ThumbnailManager = ThumbnailManager()
        self.thumb_directory: Path = Path(temp_directory.name) / "thumb"

    def __write(self, name: str, age_hours: float) -> Path:
        path: Path = self.thumb_directory / name
        path.write_bytes(b"webp")
        timestamp: float = time.time() - age_hours * 3600
        os.utime(path, (timestamp, timestamp))
        return path

    def test_cleanup_removes_only_stale_thumbnails(self):
        stale: Path = self.__write(f"{'a' * 32}.webp", age_hours=5)
        fresh: Path = self.__write(f"{'b' * 32}.webp", age_hours=1)
        stale_foreign: Path = self.__write("notes.webp", age_hours=5)
        stale_other_type: Path = self.__write(f"{'c' * 32}.png", age_hours=5)

        self.manager._ThumbnailManager__clean_thumbs_directory()

        self.assertFalse(stale.exists(), "stale cached thumbnail should be removed")
        self.assertTrue(fresh.exists(), "fresh cached thumbnail should be kept")
        self.assertTrue(stale_foreign.exists(), "files the cache didn't write should be kept")
        self.assertTrue(stale_other_type.exists(), "files the cache didn't write should be kept")
