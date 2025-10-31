#!/usr/bin/env python3
"""
Docker Compose Configuration Migration Script

This script helps migrate from the old fragmented Docker Compose files to the new
consolidated configuration. It provides validation, backup, and migration utilities.

Usage:
    python scripts/docker/migrate_compose_configs.py --validate
    python scripts/docker/migrate_compose_configs.py --backup
    python scripts/docker/migrate_compose_configs.py --migrate
    python scripts/docker/migrate_compose_configs.py --test-profiles
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


class ComposeConfigMigrator:
    """Handles migration from fragmented to consolidated Docker Compose configuration."""

    def __init__(self, repo_root: Path | None = None):
        self.repo_root = repo_root or Path(__file__).parent.parent.parent
        self.backup_dir = self.repo_root / "docker" / "backup" / f"compose-migration-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        # Original compose files to be replaced
        self.original_files = [
            "docker-compose.yml",
            "docker-compose.cet-staging.yml",
            "docker/docker-compose.dev.yml",
            "docker/docker-compose.e2e.yml",
            "docker/docker-compose.test.yml",
            "docker/neo4j.compose.override.yml"
        ]

        # New consolidated file
        self.consolidated_file = "docker-compose.consolidated.yml"

        # Profile mappings from old files to new profiles
        self.profile_mappings = {
            "docker-compose.yml": "prod",
            "docker-compose.cet-staging.yml": "cet-staging",
            "docker/docker-compose.dev.yml": "dev",
            "docker/docker-compose.e2e.yml": "e2e",
            "docker/docker-compose.test.yml": "ci-test",
            "docker/neo4j.compose.override.yml": "neo4j-standalone"
        }

    def validate_environment(self) -> bool:
        """Validate that the environment is ready for migration."""
        print("🔍 Validating environment for Docker Compose migration...")

        issues = []

        # Check if consolidated file exists
        consolidated_path = self.repo_root / self.consolidated_file
        if not consolidated_path.exists():
            issues.append(f"Consolidated file not found: {self.consolidated_file}")

        # Check if original files exist
        missing_files = []
        for file_path in self.original_files:
            full_path = self.repo_root / file_path
            if not full_path.exists():
                missing_files.append(file_path)

        if missing_files:
            print(f"⚠️  Some original files not found (this may be expected): {missing_files}")

        # Check Docker Compose version
        try:
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
                check=True
            )
            print(f"✅ Docker Compose version: {result.stdout.strip()}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            issues.append("Docker Compose not available or not v2+")

        # Check for .env file
        env_file = self.repo_root / ".env"
        if not env_file.exists():
            issues.append(".env file not found - copy .env.example to .env")

        if issues:
            print("❌ Validation failed:")
            for issue in issues:
                print(f"   - {issue}")
            return False

        print("✅ Environment validation passed")
        return True

    def backup_original_files(self) -> bool:
        """Create backup of original compose files."""
        print(f"📦 Creating backup of original files in {self.backup_dir}")

        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)

            backed_up_files = []
            for file_path in self.original_files:
                source = self.repo_root / file_path
                if source.exists():
                    # Preserve directory structure in backup
                    backup_path = self.backup_dir / file_path
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, backup_path)
                    backed_up_files.append(file_path)
                    print(f"   ✅ Backed up: {file_path}")

            # Create backup manifest
            manifest = {
                "backup_date": datetime.now().isoformat(),
                "backed_up_files": backed_up_files,
                "migration_version": "1.0",
                "repo_root": str(self.repo_root)
            }

            manifest_path = self.backup_dir / "backup_manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)

            print(f"✅ Backup completed: {len(backed_up_files)} files backed up")
            print(f"   Backup location: {self.backup_dir}")
            return True

        except Exception as e:
            print(f"❌ Backup failed: {e}")
            return False

    def test_profile_configurations(self) -> bool:
        """Test that all profile configurations work correctly."""
        print("🧪 Testing consolidated Docker Compose profile configurations...")

        test_results = {}

        for original_file, profile in self.profile_mappings.items():
            print(f"   Testing profile '{profile}' (replaces {original_file})...")

            try:
                # Test docker compose config validation
                result = subprocess.run([
                    "docker", "compose",
                    "--profile", profile,
                    "-f", str(self.repo_root / self.consolidated_file),
                    "config", "--quiet"
                ], capture_output=True, text=True, cwd=self.repo_root)

                if result.returncode == 0:
                    test_results[profile] = {"status": "✅ PASS", "error": None}
                    print(f"      ✅ Profile '{profile}' configuration valid")
                else:
                    test_results[profile] = {"status": "❌ FAIL", "error": result.stderr}
                    print(f"      ❌ Profile '{profile}' configuration invalid:")
                    print(f"         {result.stderr}")

            except Exception as e:
                test_results[profile] = {"status": "❌ ERROR", "error": str(e)}
                print(f"      ❌ Error testing profile '{profile}': {e}")

        # Summary
        passed = sum(1 for result in test_results.values() if "PASS" in result["status"])
        total = len(test_results)

        print(f"\n📊 Profile test results: {passed}/{total} passed")

        if passed == total:
            print("✅ All profile configurations are valid")
            return True
        else:
            print("❌ Some profile configurations failed validation")
            return False

    def generate_migration_commands(self) -> list[str]:
        """Generate the commands needed to complete the migration."""
        commands = [
            "# Docker Compose Configuration Migration Commands",
            "",
            "# 1. Stop any running containers",
            "docker compose down --remove-orphans",
            "",
            "# 2. Replace the main docker-compose.yml with consolidated version",
            f"mv {self.consolidated_file} docker-compose.yml",
            "",
            "# 3. Update Makefile to use new profile-based commands",
            "# (Manual step - update COMPOSE_DEV, COMPOSE_TEST, etc. variables)",
            "",
            "# 4. Test the new configuration",
            "docker compose --profile dev config --quiet",
            "docker compose --profile prod config --quiet",
            "docker compose --profile cet-staging config --quiet",
            "",
            "# 5. Start services with new profiles",
            "docker compose --profile dev up --build  # For development",
            "docker compose --profile prod up --build  # For production",
            "docker compose --profile cet-staging up --build  # For CET staging",
            "",
            "# 6. Remove old compose files (after testing)",
        ]

        for file_path in self.original_files:
            if (self.repo_root / file_path).exists():
                commands.append(f"rm {file_path}")

        return commands

    def perform_migration(self, dry_run: bool = True) -> bool:
        """Perform the actual migration."""
        print(f"🚀 {'Dry run of' if dry_run else 'Performing'} Docker Compose migration...")

        if not dry_run:
            # Create backup first
            if not self.backup_original_files():
                print("❌ Migration aborted due to backup failure")
                return False

        commands = self.generate_migration_commands()

        if dry_run:
            print("\n📋 Migration commands that would be executed:")
            for cmd in commands:
                print(f"   {cmd}")
            print("\n💡 Run with --migrate --no-dry-run to execute these commands")
            return True

        # Execute migration commands
        try:
            # Replace main compose file
            consolidated_source = self.repo_root / self.consolidated_file
            main_compose = self.repo_root / "docker-compose.yml"

            print(f"   📝 Replacing {main_compose} with {consolidated_source}")
            shutil.copy2(consolidated_source, main_compose)

            print("✅ Migration completed successfully!")
            print(f"   📦 Original files backed up to: {self.backup_dir}")
            print("   🔧 Next steps:")
            print("      1. Update Makefile to use new profile-based commands")
            print("      2. Test new configuration with: docker compose --profile dev config")
            print("      3. Remove old compose files after testing")

            return True

        except Exception as e:
            print(f"❌ Migration failed: {e}")
            return False

    def show_usage_examples(self):
        """Show usage examples for the new consolidated configuration."""
        examples = [
            ("Development", "docker compose --profile dev up --build"),
            ("Production", "docker compose --profile prod up --build"),
            ("CET Staging", "docker compose --profile cet-staging up --build"),
            ("CI Testing", "docker compose --profile ci-test up --build"),
            ("E2E Testing", "docker compose --profile e2e up --build"),
            ("Standalone Neo4j", "docker compose --profile neo4j-standalone up --build"),
            ("Tools Only", "docker compose --profile tools up --build"),
        ]

        print("\n📚 Usage examples for consolidated Docker Compose:")
        for description, command in examples:
            print(f"   {description:20} {command}")

        print("\n🔧 Environment configuration:")
        print("   Set COMPOSE_PROFILES in .env to automatically activate profiles")
        print("   Example: COMPOSE_PROFILES=dev,tools")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Docker Compose configurations to consolidated format"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate environment for migration"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backup of original files"
    )
    parser.add_argument(
        "--test-profiles",
        action="store_true",
        help="Test all profile configurations"
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Perform migration (dry run by default)"
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Actually execute migration commands"
    )
    parser.add_argument(
        "--usage",
        action="store_true",
        help="Show usage examples for new configuration"
    )

    args = parser.parse_args()

    migrator = ComposeConfigMigrator()

    success = True

    if args.validate:
        success &= migrator.validate_environment()

    if args.backup:
        success &= migrator.backup_original_files()

    if args.test_profiles:
        success &= migrator.test_profile_configurations()

    if args.migrate:
        success &= migrator.perform_migration(dry_run=not args.no_dry_run)

    if args.usage:
        migrator.show_usage_examples()

    if not any([args.validate, args.backup, args.test_profiles, args.migrate, args.usage]):
        parser.print_help()
        print("\n💡 Start with: python scripts/docker/migrate_compose_configs.py --validate")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
