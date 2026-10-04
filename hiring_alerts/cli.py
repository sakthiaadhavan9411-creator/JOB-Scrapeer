import argparse
import logging
import os
import time
from contextlib import nullcontext
from pathlib import Path

import requests
from dotenv import load_dotenv

from .config import load_config
from .dedupe import State, run_lock
from .logging_setup import event, setup_logging
from .models import AlertError
from .pipeline import process, sources
from .telegram import Telegram


def _nonnegative(value: str) -> int:
    result = int(value)
    if result < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return result


def _positive(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return result


def one_pass(args: argparse.Namespace) -> bool:
    config = load_config(args.config)
    with requests.Session() as session:
        session.headers["User-Agent"] = "linkedin-hiring-alerts/1.0"
        sender = None if args.dry_run else Telegram(os.getenv("TELEGRAM_BOT_TOKEN", ""),
                                                    os.getenv("TELEGRAM_CHAT_ID", ""), session)
        with nullcontext() if args.dry_run else run_lock(config.state_path):
            state = State(config.state_path, dry_run=args.dry_run)
            try:
                return process(config, state, sources(config, session), sender,
                               args.dry_run, args.send_backlog)
            finally:
                state.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Forward new public LinkedIn hiring posts to Telegram")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "loop"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path, default=Path("config.yaml"))
        command.add_argument("--dry-run", action="store_true")
        command.add_argument("--send-backlog", type=_nonnegative, default=0, metavar="N",
                             help="Queue up to N newest matching posts from uninitialized sources")
        if name == "loop":
            command.add_argument("--interval", type=_positive, default=900)
    args = parser.parse_args()
    setup_logging()
    load_dotenv(args.config.resolve().parent / ".env")
    try:
        while True:
            try:
                ok = one_pass(args)
            except Exception as exc:
                event("run_failed", logging.ERROR,
                      error=str(exc) if isinstance(exc, AlertError) else type(exc).__name__)
                ok = False
            if args.command == "run":
                return 0 if ok else 1
            event("loop_wait", seconds=args.interval)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        event("stopped")
        return 0
