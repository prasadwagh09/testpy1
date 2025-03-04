import fcntl
import functools
import inspect
import os
import sys
import threading
import zipfile
from types import TracebackType
from typing import Optional, Type

import anyio
import pandas as pd
from _snowflake import vectorized

from snowflake.ml.model._packager import model_packager


class FileLock:
    def __enter__(self) -> None:
        self._lock = threading.Lock()
        self._lock.acquire()
        self._fd = open("/tmp/lockfile.LOCK", "w+")
        fcntl.lockf(self._fd, fcntl.LOCK_EX)

    def __exit__(
        self, exc_type: Optional[Type[BaseException]], exc: Optional[BaseException], traceback: Optional[TracebackType]
    ) -> None:
        self._fd.close()
        self._lock.release()


# User-defined parameters
MODEL_FILE_NAME = "model.zip"
TARGET_METHOD = "predict"
MAX_BATCH_SIZE = None


# Retrieve the model
IMPORT_DIRECTORY_NAME = "snowflake_import_directory"
import_dir = sys._xoptions[IMPORT_DIRECTORY_NAME]

model_dir_name = os.path.splitext(MODEL_FILE_NAME)[0]
zip_model_path = os.path.join(import_dir, MODEL_FILE_NAME)
extracted = "/tmp/models"
extracted_model_dir_path = os.path.join(extracted, model_dir_name)

with FileLock():
    if not os.path.isdir(extracted_model_dir_path):
        with zipfile.ZipFile(zip_model_path, "r") as myzip:
            myzip.extractall(extracted_model_dir_path)

# Load the model
pk = model_packager.ModelPackager(extracted_model_dir_path)
pk.load(as_custom_model=True)
assert pk.model, "model is not loaded"
assert pk.meta, "model metadata is not loaded"

# Determine the actual runner
model = pk.model
meta = pk.meta
func = getattr(model, TARGET_METHOD)
if inspect.iscoroutinefunction(func):
    runner = functools.partial(anyio.run, func)
else:
    runner = functools.partial(func)

# Determine preprocess parameters
features = meta.signatures[TARGET_METHOD].inputs
input_cols = [feature.name for feature in features]
dtype_map = {feature.name: feature.as_dtype() for feature in features}


# Actual table function
class infer:
    @vectorized(input=pd.DataFrame, max_batch_size=MAX_BATCH_SIZE)
    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        df.columns = input_cols
        input_df = df.astype(dtype=dtype_map)
        return runner(input_df[input_cols])
