import os
import aiohttp
import asyncio
import base64
import concurrent
import hashlib
import io
import re
import threading
import traceback

from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import ParseResult, urlparse
from PIL import Image

from mcp_server_webcrawl.settings import DATA_DIRECTORY
from mcp_server_webcrawl.utils.logger import get_logger

HTTP_THREADS: int = 8
ALLOWED_THUMBNAIL_TYPES = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024  # 2MB cap

logger = get_logger()

class ThumbnailManager:
    """
    Manages thumbnail generation and caching for image files and URLs.
    """

    def __init__(self):
        DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
        assert DATA_DIRECTORY.is_dir(), f"DATA_DIRECTORY {DATA_DIRECTORY} is not a directory"
        self.__temp_directory: Path = DATA_DIRECTORY / "thumb"
        if not self.__temp_directory.is_dir():
            self.__temp_directory.mkdir(parents=True, exist_ok=True)
            os.chmod(self.__temp_directory, 0o700)

    def __md5(self, path: str) -> str:
        return hashlib.md5(path.encode()).hexdigest()

    def __is_valid_url(self, path: str) -> tuple[bool, ParseResult | None]:
        try:
            result = urlparse(path)
            return all([result.scheme, result.netloc]), result
        except:
            return False, None

    def __is_valid_file(self, path: str) -> bool:
        return Path(path).is_file()

    def __get_temp_file(self, key: str) -> Path:
        return self.__temp_directory / f"{key}.webp"

    def __get_extension(self, path: str) -> str | None:
        ext = Path(path).suffix.lower()
        if ext:
            return ext

        # try to parse extension from the path
        is_valid, parsed = self.__is_valid_url(path)
        if is_valid:
            path_parts = parsed.path.split("/")
            if path_parts:
                last_part = path_parts[-1]
                if "." in last_part:
                    return "." + last_part.split(".")[-1].lower()

        return None

    def __is_allowed_type(self, path: str) -> bool:
        ext = self.__get_extension(path)
        return ext in ALLOWED_THUMBNAIL_TYPES if ext else False

    def __clean_thumbs_directory(self):
        try:
            md5_pattern: re.Pattern = re.compile(r"^[0-9a-f]{32}$")
            cutoff_time: timedelta = datetime.now() - timedelta(hours=4)
            deleted_count: int = 0
            for file_path in self.__temp_directory.glob("*"):
                if not file_path.is_file():
                    continue
                if not md5_pattern.match(file_path.name):
                    continue
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_mtime < cutoff_time:
                    file_path.unlink()
                    deleted_count += 1
            logger.info(f"Temporary file cleanup complete: {deleted_count} files deleted")
        except Exception as ex:
            logger.error(
                f"Error during temporary file cleanup: {str(ex)}\n{traceback.format_exc()}"
            )

    def __check_content_length(self, headers) -> bool:
        """Helper to check if content length is acceptable"""
        if "Content-Length" in headers:
            content_length = int(headers["Content-Length"])
            if content_length > MAX_THUMBNAIL_BYTES:
                logger.info(
                    f"Skipping large file ({content_length} bytes > "
                    f"{MAX_THUMBNAIL_BYTES} bytes)"
                )
                return False
        return True

    async def __fetch_url(
        self, session: aiohttp.ClientSession, url: str, key: str
    ) -> str | None:
        temp_file = self.__get_temp_file(key)
        try:
            # check HEAD to get Content-Length without downloading
            async with session.head(url, timeout=1, allow_redirects=True) as head_response:
                if head_response.status == 200 and not self.__check_content_length(head_response.headers):
                    return None

            async with session.get(url, timeout=2) as response:
                if response.status != 200:
                    return None

                if not self.__check_content_length(response.headers):
                    return None

                # stream the content with a size limit
                content = bytearray()
                chunk_size = 8192  # 8KB chunks
                total_size = 0

                async for chunk in response.content.iter_chunked(chunk_size):
                    total_size += len(chunk)
                    if total_size > MAX_THUMBNAIL_BYTES:
                        logger.info(
                            f"Download exceeded size limit of {MAX_THUMBNAIL_BYTES} bytes "
                            f"while streaming"
                        )
                        return None
                    content.extend(chunk)

                return self.__process_image_data(bytes(content), temp_file)
        except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
            # http is the wild west, keep chugging
            logger.debug(f"HTTP error: {str(ex)}")
            return None

    def __process_image_data(self, data: bytes, temp_file: Path) -> str | None:
        """Process image data, save to temp file, and return base64 encoding"""
        thumbnail = self.__create_webp_thumbnail(data)
        if thumbnail is not None:
            temp_file.write_bytes(thumbnail)
            return base64.b64encode(thumbnail).decode("utf-8")
        return None

    async def __get_file(self, path: str, key: str) -> str | None:
        try:
            file_path = Path(path)
            content = file_path.read_bytes()
            temp_file = self.__get_temp_file(key)
            return self.__process_image_data(content, temp_file)
        except Exception as ex:
            logger.debug(f"File error: {str(ex)}")
            return None

    async def __process_path(
        self,
        session: aiohttp.ClientSession,
        path: str,
        results: dict[str, str | None],
        metrics: dict[str, int]
    ) -> None:
        key: str = self.__md5(path)
        temp_file: Path = self.__get_temp_file(key)

        is_valid_url, _ = self.__is_valid_url(path)
        valid_file: bool = self.__is_valid_file(path)

        if not (is_valid_url or valid_file) or not self.__is_allowed_type(path):
            return

        # cache hit
        if temp_file.exists():
            content: bytes = temp_file.read_bytes()
            results[path] = base64.b64encode(content).decode("utf-8")
            metrics["total_cached"] += 1
            return

        result: str | None = await self.__fetch_url(session, path, key) if is_valid_url else await self.__get_file(path, key)
        results[path] = result
        if result is None:
            metrics["total_errors"] += 1
        else:
            metrics["total_returned"] += 1

    async def __get_blobs_async(self, paths: list[str]) -> dict[str, str | None]:
        results = {path: None for path in paths}
        metrics = {
            "total_requested": len(paths),
            "total_returned": 0,
            "total_errors": 0,
            "total_cached": 0
        }

        async with aiohttp.ClientSession() as session:
            # Process tasks in batches of HTTP_THREADS
            for i in range(0, len(paths), HTTP_THREADS):
                batch_paths = paths[i:i + HTTP_THREADS]
                batch_tasks = [
                    self.__process_path(session, path, results, metrics)
                    for path in batch_paths
                ]
                await asyncio.gather(*batch_tasks)

        logger.info(
            f"Found {metrics['total_requested']}, fetched {metrics['total_returned']} "
            f"({metrics['total_errors']} errors, {metrics['total_cached']} cached)"
        )

        return results

    def __create_webp_thumbnail(self, image_data: bytes, size: int = 512) -> bytes | None:
        img = None
        try:
            img = Image.open(io.BytesIO(image_data))
            width, height = img.size
            max_dimension = max(width, height)

            if max_dimension > size:
                if width > height:
                    new_width = size
                    new_height = int(height * (new_width / width))
                else:
                    new_height = size
                    new_width = int(width * (new_height / height))
                img = img.resize((new_width, new_height), Image.LANCZOS)

            output = io.BytesIO()
            img.save(
                output,
                format="WEBP",
                quality=20,
                optimize=True,
                method=6  # highest compression
            )
            return output.getvalue()
        except Exception as ex:
            logger.error(f"Error creating WebP thumbnail: {str(ex)}\n{traceback.format_exc()}")
            return None
        finally:
            if img is not None:
                img.close()

    def get_thumbnails(self, paths: list[str]) -> dict[str, str | None]:
        """
        Convert URLs or file paths to base64 encoded strings.

        Args:
            paths: List of URLs or file paths to convert

        Returns:
            Dictionary mapping paths to their base64 representation or None if failed
        """
        assert paths is not None, "paths must be a list[str]"

        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.__get_blobs_async(paths))
            finally:
                loop.close()

        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                results = future.result(timeout=5)

            # start cleanup in a background thread
            cleanup_thread = threading.Thread(target=self.__clean_thumbs_directory)
            cleanup_thread.daemon = True
            cleanup_thread.start()

            return results
        except Exception as ex:
            logger.error(f"Error fetching thumbnails: {ex}\n{traceback.format_exc()}")
            return {path: None for path in paths}