import enum
import pathlib
import tempfile
import warnings
from typing import Any, Callable, Dict, List, Optional, Union

import pandas as pd

from snowflake.ml._internal import telemetry
from snowflake.ml._internal.utils import sql_identifier
from snowflake.ml.lineage import lineage_node
from snowflake.ml.model import type_hints as model_types
from snowflake.ml.model._client.ops import metadata_ops, model_ops
from snowflake.ml.model._model_composer import model_composer
from snowflake.ml.model._model_composer.model_manifest import model_manifest_schema
from snowflake.ml.model._packager.model_handlers import snowmlmodel
from snowflake.snowpark import Session, dataframe

_TELEMETRY_PROJECT = "MLOps"
_TELEMETRY_SUBPROJECT = "ModelManagement"


class ExportMode(enum.Enum):
    MODEL = "model"
    FULL = "full"


class ModelVersion(lineage_node.LineageNode):
    """Model Version Object representing a specific version of the model that could be run."""

    _model_ops: model_ops.ModelOperator
    _model_name: sql_identifier.SqlIdentifier
    _version_name: sql_identifier.SqlIdentifier
    _functions: List[model_manifest_schema.ModelFunctionInfo]

    def __init__(self) -> None:
        raise RuntimeError("ModelVersion's initializer is not meant to be used. Use `version` from model instead.")

    @classmethod
    def _ref(
        cls,
        model_ops: model_ops.ModelOperator,
        *,
        model_name: sql_identifier.SqlIdentifier,
        version_name: sql_identifier.SqlIdentifier,
    ) -> "ModelVersion":
        self: "ModelVersion" = object.__new__(cls)
        self._model_ops = model_ops
        self._model_name = model_name
        self._version_name = version_name
        self._functions = self._get_functions()
        super(cls, cls).__init__(
            self,
            session=model_ops._session,
            name=model_ops._model_client.fully_qualified_object_name(
                database_name=None, schema_name=None, object_name=model_name
            ),
            domain="model",
            version=version_name,
        )
        return self

    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, ModelVersion):
            return False
        return (
            self._model_ops == __value._model_ops
            and self._model_name == __value._model_name
            and self._version_name == __value._version_name
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(\n" f"  name='{self.model_name}',\n" f"  version='{self._version_name}',\n" f")"
        )

    @property
    def model_name(self) -> str:
        """Return the name of the model to which the model version belongs, usable as a reference in SQL."""
        return self._model_name.identifier()

    @property
    def version_name(self) -> str:
        """Return the name of the version to which the model version belongs, usable as a reference in SQL."""
        return self._version_name.identifier()

    @property
    def fully_qualified_model_name(self) -> str:
        """Return the fully qualified name of the model to which the model version belongs."""
        return self._model_ops._model_version_client.fully_qualified_object_name(None, None, self._model_name)

    @property
    @telemetry.send_api_usage_telemetry(
        project=_TELEMETRY_PROJECT,
        subproject=_TELEMETRY_SUBPROJECT,
    )
    def description(self) -> str:
        """The description for the model version. This is an alias of `comment`."""
        return self.comment

    @description.setter
    @telemetry.send_api_usage_telemetry(
        project=_TELEMETRY_PROJECT,
        subproject=_TELEMETRY_SUBPROJECT,
    )
    def description(self, description: str) -> None:
        self.comment = description

    @property
    @telemetry.send_api_usage_telemetry(
        project=_TELEMETRY_PROJECT,
        subproject=_TELEMETRY_SUBPROJECT,
    )
    def comment(self) -> str:
        """The comment to the model version."""
        statement_params = telemetry.get_statement_params(
            project=_TELEMETRY_PROJECT,
            subproject=_TELEMETRY_SUBPROJECT,
        )
        return self._model_ops.get_comment(
            database_name=None,
            schema_name=None,
            model_name=self._model_name,
            version_name=self._version_name,
            statement_params=statement_params,
        )

    @comment.setter
    @telemetry.send_api_usage_telemetry(
        project=_TELEMETRY_PROJECT,
        subproject=_TELEMETRY_SUBPROJECT,
    )
    def comment(self, comment: str) -> None:
        statement_params = telemetry.get_statement_params(
            project=_TELEMETRY_PROJECT,
            subproject=_TELEMETRY_SUBPROJECT,
        )
        return self._model_ops.set_comment(
            comment=comment,
            database_name=None,
            schema_name=None,
            model_name=self._model_name,
            version_name=self._version_name,
            statement_params=statement_params,
        )

    @telemetry.send_api_usage_telemetry(
        project=_TELEMETRY_PROJECT,
        subproject=_TELEMETRY_SUBPROJECT,
    )
    def show_metrics(self) -> Dict[str, Any]:
        """Show all metrics logged with the model version.

        Returns:
            A dictionary showing the metrics.
        """
        statement_params = telemetry.get_statement_params(
            project=_TELEMETRY_PROJECT,
            subproject=_TELEMETRY_SUBPROJECT,
        )
        return self._model_ops._metadata_ops.load(
            database_name=None,
            schema_name=None,
            model_name=self._model_name,
            version_name=self._version_name,
            statement_params=statement_params,
        )["metrics"]

    @telemetry.send_api_usage_telemetry(
        project=_TELEMETRY_PROJECT,
        subproject=_TELEMETRY_SUBPROJECT,
    )
    def get_metric(self, metric_name: str) -> Any:
        """Get the value of a specific metric.

        Args:
            metric_name: The name of the metric.

        Raises:
            KeyError: When the requested metric name does not exist.

        Returns:
            The value of the metric.
        """
        metrics = self.show_metrics()
        if metric_name not in metrics:
            raise KeyError(f"Cannot find metric with name {metric_name}.")
        return metrics[metric_name]

    @telemetry.send_api_usage_telemetry(
        project=_TELEMETRY_PROJECT,
        subproject=_TELEMETRY_SUBPROJECT,
    )
    def set_metric(self, metric_name: str, value: Any) -> None:
        """Set the value of a specific metric.

        Args:
            metric_name: The name of the metric.
            value: The value of the metric.
        """
        statement_params = telemetry.get_statement_params(
            project=_TELEMETRY_PROJECT,
            subproject=_TELEMETRY_SUBPROJECT,
        )
        metrics = self.show_metrics()
        metrics[metric_name] = value
        self._model_ops._metadata_ops.save(
            metadata_ops.ModelVersionMetadataSchema(metrics=metrics),
            database_name=None,
            schema_name=None,
            model_name=self._model_name,
            version_name=self._version_name,
            statement_params=statement_params,
        )

    @telemetry.send_api_usage_telemetry(
        project=_TELEMETRY_PROJECT,
        subproject=_TELEMETRY_SUBPROJECT,
    )
    def set_alias(self, alias_name: str) -> None:
        """Set alias to a model version.

        Args:
            alias_name: Alias to the model version.
        """
        statement_params = telemetry.get_statement_params(
            project=_TELEMETRY_PROJECT,
            subproject=_TELEMETRY_SUBPROJECT,
        )
        alias_name = sql_identifier.SqlIdentifier(alias_name)
        self._model_ops.set_alias(
            alias_name=alias_name,
            database_name=None,
            schema_name=None,
            model_name=self._model_name,
            version_name=self._version_name,
            statement_params=statement_params,
        )

    @telemetry.send_api_usage_telemetry(
        project=_TELEMETRY_PROJECT,
        subproject=_TELEMETRY_SUBPROJECT,
    )
    def delete_metric(self, metric_name: str) -> None:
        """Delete a metric from metric storage.

        Args:
            metric_name: The name of the metric to be deleted.

        Raises:
            KeyError: When the requested metric name does not exist.
        """
        statement_params = telemetry.get_statement_params(
            project=_TELEMETRY_PROJECT,
            subproject=_TELEMETRY_SUBPROJECT,
        )
        metrics = self.show_metrics()
        if metric_name not in metrics:
            raise KeyError(f"Cannot find metric with name {metric_name}.")
        del metrics[metric_name]
        self._model_ops._metadata_ops.save(
            metadata_ops.ModelVersionMetadataSchema(metrics=metrics),
            database_name=None,
            schema_name=None,
            model_name=self._model_name,
            version_name=self._version_name,
            statement_params=statement_params,
        )

    def _get_functions(self) -> List[model_manifest_schema.ModelFunctionInfo]:
        statement_params = telemetry.get_statement_params(
            project=_TELEMETRY_PROJECT,
            subproject=_TELEMETRY_SUBPROJECT,
        )
        return self._model_ops.get_functions(
            database_name=None,
            schema_name=None,
            model_name=self._model_name,
            version_name=self._version_name,
            statement_params=statement_params,
        )

    @telemetry.send_api_usage_telemetry(
        project=_TELEMETRY_PROJECT,
        subproject=_TELEMETRY_SUBPROJECT,
    )
    def show_functions(self) -> List[model_manifest_schema.ModelFunctionInfo]:
        """Show all functions information in a model version that is callable.

        Returns:
            A list of ModelFunctionInfo objects containing the following information:

            - name: The name of the function to be called (both in SQL and in Python SDK).
            - target_method: The original method name in the logged Python object.
            - signature: Python signature of the original method.
        """
        return self._functions

    @telemetry.send_api_usage_telemetry(
        project=_TELEMETRY_PROJECT,
        subproject=_TELEMETRY_SUBPROJECT,
    )
    def run(
        self,
        X: Union[pd.DataFrame, dataframe.DataFrame],
        *,
        function_name: Optional[str] = None,
        partition_column: Optional[str] = None,
        strict_input_validation: bool = False,
    ) -> Union[pd.DataFrame, dataframe.DataFrame]:
        """Invoke a method in a model version object.

        Args:
            X: The input data, which could be a pandas DataFrame or Snowpark DataFrame.
            function_name: The function name to run. It is the name used to call a function in SQL.
                Defaults to None. It can only be None if there is only 1 method.
            partition_column: The partition column name to partition by.
            strict_input_validation: Enable stricter validation for the input data. This will result value range based
                type validation to make sure your input data won't overflow when providing to the model.

        Raises:
            ValueError: When no method with the corresponding name is available.
            ValueError: When there are more than 1 target methods available in the model but no function name specified.
            ValueError: When the partition column is not a valid Snowflake identifier.

        Returns:
            The prediction data. It would be the same type dataframe as your input.
        """
        statement_params = telemetry.get_statement_params(
            project=_TELEMETRY_PROJECT,
            subproject=_TELEMETRY_SUBPROJECT,
        )

        if partition_column is not None:
            # Partition column must be a valid identifier
            partition_column = sql_identifier.SqlIdentifier(partition_column)

        functions: List[model_manifest_schema.ModelFunctionInfo] = self._functions
        if function_name:
            req_method_name = sql_identifier.SqlIdentifier(function_name).identifier()
            find_method: Callable[[model_manifest_schema.ModelFunctionInfo], bool] = (
                lambda method: method["name"] == req_method_name
            )
            target_function_info = next(
                filter(find_method, functions),
                None,
            )
            if target_function_info is None:
                raise ValueError(
                    f"There is no method with name {function_name} available in the model"
                    f" {self.fully_qualified_model_name} version {self.version_name}"
                )
        elif len(functions) != 1:
            raise ValueError(
                f"There are more than 1 target methods available in the model {self.fully_qualified_model_name}"
                f" version {self.version_name}. Please specify a `method_name` when calling the `run` method."
            )
        else:
            target_function_info = functions[0]
        return self._model_ops.invoke_method(
            method_name=sql_identifier.SqlIdentifier(target_function_info["name"]),
            method_function_type=target_function_info["target_method_function_type"],
            signature=target_function_info["signature"],
            X=X,
            database_name=None,
            schema_name=None,
            model_name=self._model_name,
            version_name=self._version_name,
            strict_input_validation=strict_input_validation,
            partition_column=partition_column,
            statement_params=statement_params,
        )

    @telemetry.send_api_usage_telemetry(
        project=_TELEMETRY_PROJECT, subproject=_TELEMETRY_SUBPROJECT, func_params_to_log=["export_mode"]
    )
    def export(self, target_path: str, *, export_mode: ExportMode = ExportMode.MODEL) -> None:
        """Export model files to a local directory.

        Args:
            target_path: Path to a local directory to export files to. A directory will be created if does not exist.
            export_mode: The mode to export the model. Defaults to ExportMode.MODEL.
                ExportMode.MODEL: All model files including environment to load the model and model weights.
                ExportMode.FULL: Additional files to run the model in Warehouse, besides all files in MODEL mode,

        Raises:
            ValueError: Raised when the target path is a file or an non-empty folder.
        """
        target_local_path = pathlib.Path(target_path)
        if target_local_path.is_file() or any(target_local_path.iterdir()):
            raise ValueError(f"Target path {target_local_path} is a file or an non-empty folder.")

        target_local_path.mkdir(parents=False, exist_ok=True)
        statement_params = telemetry.get_statement_params(
            project=_TELEMETRY_PROJECT,
            subproject=_TELEMETRY_SUBPROJECT,
        )
        self._model_ops.download_files(
            database_name=None,
            schema_name=None,
            model_name=self._model_name,
            version_name=self._version_name,
            target_path=target_local_path,
            mode=export_mode.value,
            statement_params=statement_params,
        )

    @telemetry.send_api_usage_telemetry(
        project=_TELEMETRY_PROJECT, subproject=_TELEMETRY_SUBPROJECT, func_params_to_log=["force", "options"]
    )
    def load(
        self,
        *,
        force: bool = False,
        options: Optional[model_types.ModelLoadOption] = None,
    ) -> model_types.SupportedModelType:
        """Load the underlying original Python object back from a model.
            This operation requires to have the exact the same environment as the one when logging the model, otherwise,
            the model might be not functional or some other problems might occur.

        Args:
            force: Bypass the best-effort environment validation. Defaults to False.
            options: Options to specify when loading the model, check `snowflake.ml.model.type_hints` for available
                options. Defaults to None.

        Raises:
            ValueError: Raised when the best-effort environment validation fails.

        Returns:
            The original Python object loaded from the model object.
        """
        statement_params = telemetry.get_statement_params(
            project=_TELEMETRY_PROJECT,
            subproject=_TELEMETRY_SUBPROJECT,
        )
        if not force:
            with tempfile.TemporaryDirectory() as tmp_workspace_for_validation:
                ws_path_for_validation = pathlib.Path(tmp_workspace_for_validation)
                self._model_ops.download_files(
                    database_name=None,
                    schema_name=None,
                    model_name=self._model_name,
                    version_name=self._version_name,
                    target_path=ws_path_for_validation,
                    mode="minimal",
                    statement_params=statement_params,
                )
                pk_for_validation = model_composer.ModelComposer.load(
                    ws_path_for_validation, meta_only=True, options=options
                )
                assert pk_for_validation.meta, (
                    "Unable to load model metadata for validation. "
                    f"model_name={self._model_name}, version_name={self._version_name}"
                )

                validation_errors = pk_for_validation.meta.env.validate_with_local_env(
                    check_snowpark_ml_version=(
                        pk_for_validation.meta.model_type == snowmlmodel.SnowMLModelHandler.HANDLER_TYPE
                    )
                )
                if validation_errors:
                    raise ValueError(
                        f"Unable to load this model due to following validation errors: {validation_errors}. "
                        "Make sure your local environment is the same as that when you logged the model, "
                        "or if you believe it should work, specify `force=True` to bypass this check."
                    )

        warnings.warn(
            "Loading model requires to have the exact the same environment as the one when "
            "logging the model, otherwise, the model might be not functional or "
            "some other problems might occur.",
            category=RuntimeWarning,
            stacklevel=2,
        )

        # We need the folder to be existed.
        workspace = pathlib.Path(tempfile.mkdtemp())
        self._model_ops.download_files(
            database_name=None,
            schema_name=None,
            model_name=self._model_name,
            version_name=self._version_name,
            target_path=workspace,
            mode="model",
            statement_params=statement_params,
        )
        pk = model_composer.ModelComposer.load(workspace, meta_only=False, options=options)
        assert pk.model, (
            "Unable to load model. "
            f"model_name={self._model_name}, version_name={self._version_name}, metadata={pk.meta}"
        )
        return pk.model

    @staticmethod
    def _load_from_lineage_node(session: Session, name: str, version: str) -> "ModelVersion":
        database_name_id, schema_name_id, model_name_id = sql_identifier.parse_fully_qualified_name(name)
        if not database_name_id or not schema_name_id:
            raise ValueError("name should be fully qualifed.")

        return ModelVersion._ref(
            model_ops.ModelOperator(
                session,
                database_name=database_name_id,
                schema_name=schema_name_id,
            ),
            model_name=model_name_id,
            version_name=sql_identifier.SqlIdentifier(version),
        )


lineage_node.DOMAIN_LINEAGE_REGISTRY["model"] = ModelVersion
