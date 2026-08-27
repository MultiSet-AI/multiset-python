"""Command-line entry points.

This is the ONLY layer that prints, prompts, or sets an exit code. Everything
under multiset.unitree.go2/ returns values and raises exceptions; if a function both
computes and prints, it is in the wrong place.
"""
