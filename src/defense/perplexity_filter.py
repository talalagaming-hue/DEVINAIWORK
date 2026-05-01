"""
Perplexity-based defense against adversarial inputs.

Implements the perplexity filter from Alon & Kamfonas 2023:
"Detecting Language Model Attacks with Perplexity"
https://arxiv.org/abs/2308.14132

The filter detects adversarial suffixes by measuring the perplexity
of input text under a reference language model. Adversarial suffixes
tend to have unusually high perplexity.
"""

import torch
from typing import Optional
from transformers import AutoModelForCausalLM, AutoTokenizer


class PerplexityFilter:
    """
    Perplexity-based detector for adversarial inputs.

    Uses a reference GPT-2 model to compute perplexity of input text.
    Flags inputs with perplexity exceeding a calibrated threshold
    as potential adversarial attacks.

    Attributes:
        model_name: HF model identifier for perplexity computation
        threshold: Perplexity threshold (inputs above this are flagged)
        device: Torch device for inference
    """

    def __init__(
        self,
        model_name: str = "gpt2",
        threshold: float = 100.0,
        device: Optional[str] = None,
    ):
        """
        Initialize the perplexity filter.

        Args:
            model_name: HuggingFace model ID (default: gpt2)
            threshold: Perplexity threshold for adversarial detection
            device: Torch device (auto-detected if None)
        """
        self.model_name = model_name
        self.threshold = threshold
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(model_name).to(self.device)
        self.model.eval()

    def compute_perplexity(self, text: str) -> float:
        """
        Compute perplexity of a text string under the reference model.

        Args:
            text: Input text to evaluate

        Returns:
            Perplexity score (lower = more natural)
        """
        encodings = self.tokenizer(text, return_tensors="pt").to(self.device)

        with torch.no_grad():
            outputs = self.model(**encodings, labels=encodings["input_ids"])
            loss = outputs.loss

        return torch.exp(loss).item()

    def is_adversarial(self, text: str) -> bool:
        """
        Check if input text is likely adversarial.

        Args:
            text: Input text to check

        Returns:
            True if perplexity exceeds threshold (suspected adversarial)
        """
        ppl = self.compute_perplexity(text)
        return ppl > self.threshold

    def analyze(self, text: str) -> dict:
        """
        Full analysis of input text.

        Args:
            text: Input text to analyze

        Returns:
            Dictionary with perplexity score, verdict, and metadata
        """
        ppl = self.compute_perplexity(text)
        return {
            "text": text,
            "perplexity": round(ppl, 2),
            "threshold": self.threshold,
            "is_adversarial": ppl > self.threshold,
            "model": self.model_name,
        }
