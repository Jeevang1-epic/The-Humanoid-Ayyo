#!/usr/bin/env python3

# Copyright 2026 Ayyo Project Authors

"""Emit a report after one fixed repository smoke adapter completed its checks."""

import argparse
import json

from ayyo_developmental_scenarios import recorded_success_report, SCENARIO_CATALOG


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Record a completed fixed developmental scenario check.'
    )
    parser.add_argument(
        '--scenario',
        required=True,
        choices=tuple(item.scenario_id for item in SCENARIO_CATALOG),
    )
    arguments = parser.parse_args()
    report = recorded_success_report(arguments.scenario)
    print(json.dumps(report.as_dict(), sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
