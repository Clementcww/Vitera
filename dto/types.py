from typing import NewType

# Text that has passed redaction. service/redact.py is the ONLY module allowed
# to produce one. Every model-facing signature takes SafeText, so a raw str
# reaching the encoder is a type error, not a runtime surprise.
SafeText = NewType("SafeText", str)
