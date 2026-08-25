#!/usr/bin/env python3

"""Create one smoke-owned session with foreground-style signal dispositions."""

from __future__ import annotations

import os
import signal
import sys


def main() -> int:
    """Become a session leader and replace this process with the launch command."""
    if len(sys.argv) < 2:
        print('smoke_session.py requires a command', file=sys.stderr)
        return 2
    os.setsid()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    os.execvp(sys.argv[1], sys.argv[1:])
    return 127


if __name__ == '__main__':
    raise SystemExit(main())
