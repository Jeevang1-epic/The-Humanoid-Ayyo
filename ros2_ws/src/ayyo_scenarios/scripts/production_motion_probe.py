#!/usr/bin/env python3

# Copyright 2026 Ayyo Project Authors

"""Emit the deterministic real-contract production-motion boundary result."""

import json

from ayyo_developmental_scenarios import evaluate_production_motion_boundary


def main() -> None:
    result = evaluate_production_motion_boundary()
    print(json.dumps(result.as_dict(), sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
