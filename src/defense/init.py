"""
NLP Defense Toolkit — Evaluation Framework.

This package provides evaluation infrastructure for benchmarking
defenses against adversarial attacks on language models.
"""

from .perplexity_filter import PerplexityFilter
from .eval_harness import EvalHarness

all = ["PerplexityFilter", "EvalHarness"]
