#!/bin/bash
# Lists master-style code in src/ that the linux branch shouldn't pick up: package or relative imports,
# src.module.name references, Windows paths, image or font paths relative to src/, and a __main__ block
# in scoreSheetBot.py.
# Prints "file: line" without line numbers, sorted, so before/after runs can be diffed.
cd "$(git rev-parse --show-toplevel)" || exit 1
{
  grep -rhHE "^\s*(from|import) +(src\b|\.)" src --include=*.py
  grep -rhHE "\bsrc\.[a-z_]+\." src --include=*.py
  grep -rhH "C:/" src --include=*.py
  grep -rhHE "[\"'\''](img|font)/" src --include=*.py
  grep -hH "__name__ == '__main__'" src/scoreSheetBot.py
} | sed 's/^\([^:]*\):\s*/\1: /' | sort
exit 0
