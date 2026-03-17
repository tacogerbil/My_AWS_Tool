import sys
import argparse
import os
import logging
from typing import Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from adapters.mock_adapter import MockAdapter
from adapters.config_adapter import ConfigAdapter
from core.services import ResourceService
from ui.cli import CommandLineInterface

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("main")


def main() -> None:
    """Composition root. CLI flags override persisted config."""
    parser = argparse.ArgumentParser(description="AWS Tool - VM Import/Export & Resource Manager")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode")
    parser.add_argument("--mock", action="store_true", help="Use Mock Adapter (Offline Mode)")
    parser.add_argument("--region", default=None, help="Override AWS region")
    parser.add_argument("--profile", default=None, help="Override AWS profile name")

    args, remaining_argv = parser.parse_known_args()

    # Load persisted config; CLI flags override when provided
    config_adapter = ConfigAdapter()
    config = config_adapter.load()

    region: str = args.region or config.region
    profile: Optional[str] = args.profile or config.aws_profile

    adapter = None
    if args.mock:
        logger.info("Initializing with MOCK Adapter...")
        adapter = MockAdapter()
    else:
        logger.info("Initializing with AWS Adapter (profile=%s, region=%s)...", profile, region)
        try:
            from adapters.aws_adapter import AwsAdapter
            adapter = AwsAdapter(profile_name=profile, region=region)
        except ImportError:
            logger.critical("boto3 not installed. Run: pip install boto3")
            sys.exit(1)
        except Exception as exc:
            logger.critical("Failed to initialize AwsAdapter: %s", exc)
            sys.exit(1)

    service = ResourceService(adapter)

    if args.cli:
        logger.info("Starting in CLI mode...")
        cli = CommandLineInterface(service)
        cli.run(remaining_argv)
    else:
        logger.info("Starting in GUI mode...")
        try:
            from PySide6.QtWidgets import QApplication
            from tools.vm_importer.ui.main_window import LandingWindow

            app = QApplication(sys.argv)
            window = LandingWindow(service, current_region=region)
            window.show()
            sys.exit(app.exec())
        except ImportError:
            logger.critical("PySide6 not installed. Run: pip install PySide6")
            sys.exit(1)
        except Exception as exc:
            logger.critical("Unhandled GUI Error: %s", exc)
            sys.exit(1)


if __name__ == "__main__":
    main()
