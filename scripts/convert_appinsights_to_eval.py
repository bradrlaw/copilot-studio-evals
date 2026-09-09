#!/usr/bin/env python3
"""Compatibility entry point for the generic Application Insights converter.

New automation may use either this stable filename or
convert_appinsights_to_eval_general.py. Both execute the same agent-agnostic
implementation.
"""

from convert_appinsights_to_eval_general import main


if __name__ == "__main__":
    main()
