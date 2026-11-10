# Imported before any test module, so the project picks the model cache (HF_HOME) before a test imports transformers
import truth_guardian  # noqa: F401

import os  # noqa: E402

# Tests never reach the internet: the free online services' keys in free.local.env are for the app, not for the tests.
# A test that wants a second opinion stands one in itself (rag/second.py, D-200).
os.environ["TG_SECOND_OPINION"] = "0"
os.environ["TG_ACTIVITY_FILES"] = "0"  # the activity log stays in memory: tests never write to runtime/logs
