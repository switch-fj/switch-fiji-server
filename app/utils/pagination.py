from typing import Optional

from cryptography.fernet import Fernet

from app.core.config import Config
from app.core.exceptions import BadRequest


class Pagination:
    CURSOR_SECRET = Config.CURSOR_SECRET.encode("utf-8")
    fernet = Fernet(CURSOR_SECRET)

    @staticmethod
    def encrypt_cursor(cursor: int):
        if cursor < 0:
            raise BadRequest("Cursor can't be negative")
        bytes_representation = cursor.to_bytes(8, byteorder="big")
        encrypted_bytes = Pagination.fernet.encrypt(bytes_representation)
        return encrypted_bytes.decode()

    @staticmethod
    def decrypt_cursor(encrypted_cursor: str):
        encrypted_bytes = encrypted_cursor.encode("utf-8")
        decrypted_bytes = Pagination.fernet.decrypt(encrypted_bytes)
        decrypted_number = int.from_bytes(decrypted_bytes, byteorder="big")
        return decrypted_number

    @staticmethod
    def get_current_and_total_pages(limit: int, total: Optional[int] = None, offset: Optional[int] = None):
        if limit <= 0:
            raise ValueError("Limit must be greater than 0")

        if offset is None:
            offset = 0
        elif offset < 0:
            raise ValueError("Offset must be greater than 0")

        if total is None:
            total = 0
        if total < 0:
            raise ValueError("Total must be greater than 0")

        current_page = (offset // limit) + 1
        total_pages = max(1, (total + limit - 1) // limit) if total > 0 else 1

        return current_page, total_pages
