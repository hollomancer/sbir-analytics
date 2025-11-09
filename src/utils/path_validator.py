"""Path validation utilities for SBIR ETL Pipeline.

This module provides utilities for validating file system paths on startup,
ensuring that required directories exist and files are accessible.
"""

from pathlib import Path

from loguru import logger

from ..config.schemas import PathsConfig
from ..exceptions import FileSystemError


class PathValidator:
    """Validates file system paths and optionally creates missing directories."""

    def __init__(self, paths_config: PathsConfig, project_root: Path | None = None):
        """Initialize path validator.

        Args:
            paths_config: PathsConfig instance from pipeline configuration
            project_root: Project root directory (defaults to current working directory)
        """
        self.paths_config = paths_config
        self.project_root = project_root or Path.cwd()
        self.validation_errors: list[str] = []

    def validate_all_paths(
        self, create_missing_dirs: bool = False, require_files_exist: bool = False
    ) -> bool:
        """Validate all configured paths.

        Args:
            create_missing_dirs: If True, create missing parent directories
            require_files_exist: If True, fail if files don't exist (for strict validation)

        Returns:
            True if all validations pass, False otherwise

        Side effects:
            Populates self.validation_errors with any validation failures
        """
        self.validation_errors = []

        # Validate directory paths (these should exist or be creatable)
        directory_paths = [
            "data_root",
            "raw_data",
            "usaspending_dump_dir",
            "transition_dump_dir",
            "scripts_output",
        ]

        for path_key in directory_paths:
            try:
                path = self.paths_config.resolve_path(
                    path_key, create_parent=False, project_root=self.project_root
                )
                self.validate_directory_path(
                    path=path, path_key=path_key, create_if_missing=create_missing_dirs
                )
            except Exception as e:
                self.validation_errors.append(f"Error validating directory '{path_key}': {e}")

        # Validate file paths (these may not exist yet, depending on pipeline stage)
        file_paths = [
            "usaspending_dump_file",
            "transition_contracts_output",
            "transition_vendor_filters",
        ]

        for path_key in file_paths:
            try:
                path = self.paths_config.resolve_path(
                    path_key, create_parent=create_missing_dirs, project_root=self.project_root
                )
                self.validate_file_path(
                    path=path, path_key=path_key, must_exist=require_files_exist
                )
            except Exception as e:
                self.validation_errors.append(f"Error validating file '{path_key}': {e}")

        # Log validation results
        if self.validation_errors:
            logger.warning(
                "Path validation completed with errors",
                extra={
                    "error_count": len(self.validation_errors),
                    "errors": self.validation_errors,
                },
            )
            return False
        else:
            logger.info(
                "Path validation completed successfully",
                extra={"validated_paths": len(directory_paths) + len(file_paths)},
            )
            return True

    def validate_directory_path(
        self, path: Path, path_key: str, create_if_missing: bool = False
    ) -> None:
        """Validate a single directory path.

        Args:
            path: Resolved Path object to validate
            path_key: Configuration key name (for error messages)
            create_if_missing: If True, create the directory if it doesn't exist

        Raises:
            FileSystemError: If directory doesn't exist and create_if_missing=False
        """
        if not path.exists():
            if create_if_missing:
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    logger.info(
                        "Created missing directory",
                        extra={"path_key": path_key, "path": str(path)},
                    )
                except OSError as e:
                    raise FileSystemError(
                        message=f"Failed to create directory for '{path_key}'",
                        component="path_validator",
                        operation="create_directory",
                        details={"path": str(path), "error": str(e)},
                        error_code=4003,  # FILE_WRITE_FAILED
                    ) from e
            else:
                logger.warning(
                    "Directory does not exist", extra={"path_key": path_key, "path": str(path)}
                )
        elif not path.is_dir():
            raise FileSystemError(
                message=f"Path exists but is not a directory: '{path_key}'",
                component="path_validator",
                operation="validate_directory",
                details={"path": str(path)},
                error_code=4001,  # FILE_NOT_FOUND
            )
        else:
            logger.debug(
                "Directory validated successfully", extra={"path_key": path_key, "path": str(path)}
            )

    def validate_file_path(self, path: Path, path_key: str, must_exist: bool = False) -> None:
        """Validate a single file path.

        Args:
            path: Resolved Path object to validate
            path_key: Configuration key name (for error messages)
            must_exist: If True, raise error if file doesn't exist

        Raises:
            FileSystemError: If file must exist but doesn't, or if parent directory
                           doesn't exist
        """
        # Check parent directory exists
        if not path.parent.exists():
            raise FileSystemError(
                message=f"Parent directory doesn't exist for '{path_key}'",
                component="path_validator",
                operation="validate_file",
                details={"path": str(path), "parent": str(path.parent)},
                error_code=4001,  # FILE_NOT_FOUND
            )

        # Check file existence
        if not path.exists():
            if must_exist:
                raise FileSystemError(
                    message=f"Required file doesn't exist: '{path_key}'",
                    component="path_validator",
                    operation="validate_file",
                    details={"path": str(path)},
                    error_code=4001,  # FILE_NOT_FOUND
                )
            else:
                logger.debug(
                    "File does not exist (OK for outputs)",
                    extra={"path_key": path_key, "path": str(path)},
                )
        elif path.is_dir():
            raise FileSystemError(
                message=f"Path is a directory, expected file: '{path_key}'",
                component="path_validator",
                operation="validate_file",
                details={"path": str(path)},
                error_code=4002,  # FILE_READ_FAILED
            )
        else:
            logger.debug(
                "File validated successfully", extra={"path_key": path_key, "path": str(path)}
            )

    def get_validation_errors(self) -> list[str]:
        """Get list of validation errors from the last validation run.

        Returns:
            List of error messages
        """
        return self.validation_errors.copy()

    def print_validation_summary(self) -> None:
        """Print a human-readable summary of validation results."""
        if self.validation_errors:
            print("\n⚠️  Path Validation Errors:")
            for i, error in enumerate(self.validation_errors, 1):
                print(f"  {i}. {error}")
            print(
                f"\nTotal errors: {len(self.validation_errors)}\n"
                "Fix these paths in your configuration or set environment variables.\n"
                "See docs/configuration/paths.md for details."
            )
        else:
            print("✓ All paths validated successfully")


def validate_paths_on_startup(
    create_missing_dirs: bool = True, require_files_exist: bool = False
) -> bool:
    """Convenience function to validate paths on application startup.

    Args:
        create_missing_dirs: If True, create missing parent directories
        require_files_exist: If True, fail if files don't exist

    Returns:
        True if validation passes, False otherwise

    Example:
        >>> from src.utils.path_validator import validate_paths_on_startup
        >>> if not validate_paths_on_startup():
        ...     raise SystemExit("Path validation failed")
    """
    from ..config.loader import get_config

    config = get_config()
    validator = PathValidator(config.paths)

    success = validator.validate_all_paths(
        create_missing_dirs=create_missing_dirs, require_files_exist=require_files_exist
    )

    if not success:
        validator.print_validation_summary()

    return success
