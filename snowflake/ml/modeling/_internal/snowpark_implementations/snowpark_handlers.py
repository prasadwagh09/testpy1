import importlib
import inspect
import os
import posixpath
from typing import Any, Dict, List, Optional
from uuid import uuid4

import cloudpickle as cp
import pandas as pd

from snowflake.ml._internal import telemetry
from snowflake.ml._internal.utils import identifier, snowpark_dataframe_utils
from snowflake.ml._internal.utils.query_result_checker import SqlResultValidator
from snowflake.ml._internal.utils.temp_file_utils import (
    cleanup_temp_files,
    get_temp_file_path,
)
from snowflake.ml.modeling._internal.estimator_utils import handle_inference_result
from snowflake.snowpark import DataFrame, Session
from snowflake.snowpark._internal.utils import (
    TempObjectType,
    random_name_for_temp_object,
)
from snowflake.snowpark.functions import pandas_udf, sproc
from snowflake.snowpark.types import PandasSeries

cp.register_pickle_by_value(inspect.getmodule(get_temp_file_path))
cp.register_pickle_by_value(inspect.getmodule(identifier.get_inferred_name))
cp.register_pickle_by_value(inspect.getmodule(handle_inference_result))

_PROJECT = "ModelDevelopment"


def _get_rand_id() -> str:
    """
    Generate random id to be used in sproc and stage names.

    Returns:
        Random id string usable in sproc, table, and stage names.
    """
    return str(uuid4()).replace("-", "_").upper()


class SnowparkTransformHandlers:
    def __init__(
        self,
        dataset: DataFrame,
        estimator: object,
        class_name: str,
        subproject: str,
        autogenerated: Optional[bool] = False,
    ) -> None:
        """
        Args:
            dataset: The dataset to run transform functions on.
            estimator: The estimator used to run transforms.
            class_name: class name to be used in telemetry.
            subproject: subproject to be used in telemetry.
            autogenerated: Whether the class was autogenerated from a template.
        """
        self.dataset = dataset
        self.estimator = estimator
        self._class_name = class_name
        self._subproject = subproject
        self._autogenerated = autogenerated

    def batch_inference(
        self,
        inference_method: str,
        input_cols: List[str],
        expected_output_cols: List[str],
        pass_through_cols: List[str],
        session: Session,
        dependencies: List[str],
        expected_output_cols_type: Optional[str] = "",
        *args: Any,
        **kwargs: Any,
    ) -> DataFrame:
        """Run batch inference on the given dataset.

        Args:
            session: An active Snowpark Session.
            dependencies: List of dependencies for the transformer.
            inference_method: the name of the method used by `estimator` to run inference.
            input_cols: List of feature columns for inference.
            pass_through_cols: columns in the dataset not used in inference.
            expected_output_cols: column names (in order) of the output dataset.
            expected_output_cols_type: Expected type of the output columns.
            args: additional positional arguments.
            kwargs: additional keyword args.

        Returns:
            A new dataset of the same type as the input dataset.
        """

        dataset = self.dataset
        estimator = self.estimator
        # Register vectorized UDF for batch inference
        batch_inference_udf_name = random_name_for_temp_object(TempObjectType.FUNCTION)
        snowpark_cols = dataset.select(input_cols).columns
        dataset = snowpark_dataframe_utils.cast_snowpark_dataframe_column_types(dataset)

        statement_params = telemetry.get_function_usage_statement_params(
            project=_PROJECT,
            subproject=self._subproject,
            function_name=telemetry.get_statement_params_full_func_name(inspect.currentframe(), self._class_name),
            api_calls=[pandas_udf],
            custom_tags=dict([("autogen", True)]) if self._autogenerated else None,
        )

        @pandas_udf(  # type: ignore[arg-type, misc]
            is_permanent=False,
            name=batch_inference_udf_name,
            packages=dependencies,  # type: ignore[arg-type]
            replace=True,
            session=session,
            statement_params=statement_params,
        )
        def vec_batch_infer(ds: PandasSeries[dict]) -> PandasSeries[dict]:  # type: ignore[type-arg]
            import numpy as np  # noqa: F401
            import pandas as pd

            input_df = pd.json_normalize(ds)

            # pd.json_normalize() doesn't remove quotes around quoted identifiers like snowpakr_df.to_pandas().
            # But trained models have unquoted input column names saved in internal state if trained using snowpark_df
            # or quoted input column names saved in internal state if trained using pandas_df.
            # Model expects exact same columns names in the input df for predict call.

            input_df = input_df[input_cols]  # Select input columns with quoted column names.
            if hasattr(estimator, "feature_names_in_"):
                missing_features = []
                for i, f in enumerate(getattr(estimator, "feature_names_in_", {})):
                    if i >= len(input_cols) or (input_cols[i] != f and snowpark_cols[i] != f):
                        missing_features.append(f)

                if len(missing_features) > 0:
                    raise ValueError(
                        "The feature names should match with those that were passed during fit.\n"
                        f"Features seen during fit call but not present in the input: {missing_features}\n"
                        f"Features in the input dataframe : {input_cols}\n"
                    )
                input_df.columns = getattr(estimator, "feature_names_in_", {})
            else:
                # Just rename the column names to unquoted identifiers.
                input_df.columns = snowpark_cols  # Replace the quoted columns identifier with unquoted column ids.
            inference_res = getattr(estimator, inference_method)(input_df, *args, **kwargs)

            transformed_numpy_array, output_cols = handle_inference_result(
                inference_res=inference_res,
                output_cols=expected_output_cols,
                inference_method=inference_method,
                within_udf=True,
            )

            if len(transformed_numpy_array.shape) > 1:
                if transformed_numpy_array.shape[1] != len(output_cols):
                    series = pd.Series(transformed_numpy_array.tolist())
                    transformed_pandas_df = pd.DataFrame(series, columns=output_cols)
                else:
                    transformed_pandas_df = pd.DataFrame(transformed_numpy_array.tolist(), columns=output_cols)
            else:
                transformed_pandas_df = pd.DataFrame(transformed_numpy_array, columns=output_cols)

            return transformed_pandas_df.to_dict("records")  # type: ignore[no-any-return]

        batch_inference_table_name = f"SNOWML_BATCH_INFERENCE_INPUT_TABLE_{_get_rand_id()}"

        # Run Transform
        query_from_df = str(dataset.queries["queries"][0])

        outer_select_list = pass_through_cols[:]
        inner_select_list = pass_through_cols[:]

        outer_select_list.extend(
            [
                "{object_name}:{column_name}{udf_datatype} as {column_name}".format(
                    object_name=batch_inference_udf_name,
                    column_name=identifier.get_inferred_name(c),
                    udf_datatype=(f"::{expected_output_cols_type}" if expected_output_cols_type else ""),
                )
                for c in expected_output_cols
            ]
        )

        inner_select_list.extend(
            [
                "{udf_name}(object_construct_keep_null({input_cols_dict})) AS {udf_name}".format(
                    udf_name=batch_inference_udf_name,
                    input_cols_dict=", ".join([f"'{c}', {c}" for c in input_cols]),
                )
            ]
        )

        sql = """WITH {input_table_name} AS ({query})
                    SELECT
                      {outer_select_stmt}
                    FROM (
                      SELECT
                        {inner_select_stmt}
                      FROM {input_table_name}
                    )
               """.format(
            input_table_name=batch_inference_table_name,
            query=query_from_df,
            outer_select_stmt=", ".join(outer_select_list),
            inner_select_stmt=", ".join(inner_select_list),
        )

        return session.sql(sql)

    def score(
        self,
        input_cols: List[str],
        label_cols: List[str],
        session: Session,
        dependencies: List[str],
        score_sproc_imports: List[str],
        sample_weight_col: Optional[str] = None,
        *args: Any,
        **kwargs: Any,
    ) -> float:
        """Score the given test dataset.

        Args:
            session: An active Snowpark Session.
            dependencies: score function dependencies.
            score_sproc_imports: imports for score stored procedure.
            input_cols: List of feature columns for inference.
            label_cols: List of label columns for scoring.
            sample_weight_col: A column assigning relative weights to each row for scoring.
            args: additional positional arguments.
            kwargs: additional keyword args.

        Returns:
            An accuracy score for the model on the given test data.
        """

        dataset = self.dataset
        estimator = self.estimator
        dataset = snowpark_dataframe_utils.cast_snowpark_dataframe_column_types(dataset)

        # Extract queries that generated the dataframe. We will need to pass it to score procedure.
        queries = dataset.queries["queries"]

        # Create a temp file and dump the score to that file.
        local_score_file_name = get_temp_file_path()
        with open(local_score_file_name, mode="w+b") as local_score_file:
            cp.dump(estimator, local_score_file)

        # Create temp stage to run score.
        score_stage_name = random_name_for_temp_object(TempObjectType.STAGE)
        assert session is not None  # keep mypy happy
        stage_creation_query = f"CREATE OR REPLACE TEMPORARY STAGE {score_stage_name};"
        SqlResultValidator(session=session, query=stage_creation_query).has_dimensions(
            expected_rows=1, expected_cols=1
        ).validate()

        # Use posixpath to construct stage paths
        stage_score_file_name = posixpath.join(score_stage_name, os.path.basename(local_score_file_name))
        score_sproc_name = random_name_for_temp_object(TempObjectType.PROCEDURE)
        statement_params = telemetry.get_function_usage_statement_params(
            project=_PROJECT,
            subproject=self._subproject,
            function_name=telemetry.get_statement_params_full_func_name(
                inspect.currentframe(), self.__class__.__name__
            ),
            api_calls=[sproc],
            custom_tags=dict([("autogen", True)]) if self._autogenerated else None,
        )
        # Put locally serialized score on stage.
        session.file.put(
            local_score_file_name,
            stage_score_file_name,
            auto_compress=False,
            overwrite=True,
            statement_params=statement_params,
        )

        @sproc(  # type: ignore[misc]
            is_permanent=False,
            name=score_sproc_name,
            packages=dependencies,  # type: ignore[arg-type]
            replace=True,
            session=session,
            statement_params=statement_params,
            anonymous=True,
        )
        def score_wrapper_sproc(
            session: Session,
            sql_queries: List[str],
            stage_score_file_name: str,
            input_cols: List[str],
            label_cols: List[str],
            sample_weight_col: Optional[str],
            score_statement_params: Dict[str, str],
        ) -> float:
            import inspect
            import os

            import cloudpickle as cp

            for import_name in score_sproc_imports:
                importlib.import_module(import_name)

            for query in sql_queries[:-1]:
                _ = session.sql(query).collect(statement_params=score_statement_params)
            sp_df = session.sql(sql_queries[-1])
            df: pd.DataFrame = sp_df.to_pandas(statement_params=score_statement_params)
            df.columns = sp_df.columns

            local_score_file_name = get_temp_file_path()
            session.file.get(stage_score_file_name, local_score_file_name, statement_params=score_statement_params)

            local_score_file_name_path = os.path.join(local_score_file_name, os.listdir(local_score_file_name)[0])
            with open(local_score_file_name_path, mode="r+b") as local_score_file_obj:
                estimator = cp.load(local_score_file_obj)

            argspec = inspect.getfullargspec(estimator.score)
            if "X" in argspec.args:
                args = {"X": df[input_cols]}
            elif "X_test" in argspec.args:
                args = {"X_test": df[input_cols]}
            else:
                raise RuntimeError("Neither 'X' or 'X_test' exist in argument")

            if label_cols:
                label_arg_name = "Y" if "Y" in argspec.args else "y"
                args[label_arg_name] = df[label_cols].squeeze()

            if sample_weight_col is not None and "sample_weight" in argspec.args:
                args["sample_weight"] = df[sample_weight_col].squeeze()

            result: float = estimator.score(**args)
            return result

        # Call score sproc
        score_statement_params = telemetry.get_function_usage_statement_params(
            project=_PROJECT,
            subproject=self._subproject,
            function_name=telemetry.get_statement_params_full_func_name(
                inspect.currentframe(), self.__class__.__name__
            ),
            api_calls=[Session.call],
            custom_tags=dict([("autogen", True)]) if self._autogenerated else None,
        )

        kwargs = telemetry.get_sproc_statement_params_kwargs(score_wrapper_sproc, score_statement_params)
        score: float = score_wrapper_sproc(
            session,
            queries,
            stage_score_file_name,
            input_cols,
            label_cols,
            sample_weight_col,
            score_statement_params,
            **kwargs,
        )

        cleanup_temp_files([local_score_file_name])

        return score
