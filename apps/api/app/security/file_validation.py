import os
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class FileValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    file_type: str
    file_size_bytes: int
    issues: list[str]
    reason_codes: list[str]


class FileValidator:
    """Validates files for ingestion against allowed extensions, sizes, and malicious content."""

    ALLOWED_EXTENSIONS: ClassVar[set[str]] = {".md", ".markdown", ".txt", ".pdf"}
    DANGEROUS_EXTENSIONS: ClassVar[set[str]] = {
        ".exe",
        ".bat",
        ".cmd",
        ".sh",
        ".py",
        ".js",
        ".vbs",
        ".ps1",
        ".jar",
        ".bin",
    }
    MAX_FILE_SIZE_BYTES: ClassVar[int] = 10 * 1024 * 1024  # 10 MB

    def validate_file_path(self, file_path: str | Path) -> FileValidationResult:
        path = Path(file_path)
        issues: list[str] = []
        reason_codes: list[str] = []

        if not path.exists():
            return FileValidationResult(
                is_valid=False,
                file_type="UNKNOWN",
                file_size_bytes=0,
                issues=[f"File does not exist: {file_path}"],
                reason_codes=["FILE_NOT_FOUND"],
            )

        if not path.is_file():
            return FileValidationResult(
                is_valid=False,
                file_type="DIRECTORY",
                file_size_bytes=0,
                issues=[f"Path is not a regular file: {file_path}"],
                reason_codes=["NOT_A_REGULAR_FILE"],
            )

        suffix = path.suffix.lower()
        if suffix in self.DANGEROUS_EXTENSIONS:
            issues.append(f"Dangerous file extension prohibited: {suffix}")
            reason_codes.append("DANGEROUS_FILE_EXTENSION")

        if suffix not in self.ALLOWED_EXTENSIONS:
            allowed_list = ", ".join(sorted(self.ALLOWED_EXTENSIONS))
            issues.append(f"File extension '{suffix}' not in allowed list: {allowed_list}")
            reason_codes.append("UNSUPPORTED_EXTENSION")

        try:
            size = os.path.getsize(path)
        except OSError as exc:
            return FileValidationResult(
                is_valid=False,
                file_type=suffix or "UNKNOWN",
                file_size_bytes=0,
                issues=[f"Failed to check file size: {exc}"],
                reason_codes=["FILE_ACCESS_ERROR"],
            )

        if size > self.MAX_FILE_SIZE_BYTES:
            issues.append(f"File size {size} exceeds max limit of {self.MAX_FILE_SIZE_BYTES} bytes")
            reason_codes.append("FILE_SIZE_EXCEEDED")

        is_valid = len(issues) == 0
        if is_valid:
            reason_codes.append("FILE_VALIDATION_PASSED")

        return FileValidationResult(
            is_valid=is_valid,
            file_type=suffix.lstrip(".").upper() or "UNKNOWN",
            file_size_bytes=size,
            issues=issues,
            reason_codes=reason_codes,
        )
