#
# This code is auto-generated using the sklearn_wrapper_template.py_template template.
# Do not modify the auto-generated code(except automatic reformatting by precommit hooks).
#
from typing import Any, Dict, Iterable, List, Optional, Set, Union

import cloudpickle as cp
import numpy as np
import pandas as pd
import sklearn.model_selection
from sklearn.utils.metaestimators import available_if

from snowflake.ml._internal import telemetry
from snowflake.ml._internal.exceptions import error_codes, exceptions
from snowflake.ml._internal.utils import identifier, pkg_version_utils
from snowflake.ml.model._signatures import utils as model_signature_utils
from snowflake.ml.model.model_signature import (
    BaseFeatureSpec,
    DataType,
    FeatureSpec,
    ModelSignature,
    _infer_signature,
)
from snowflake.ml.modeling._internal.estimator_protocols import TransformerHandlers
from snowflake.ml.modeling._internal.estimator_utils import (
    gather_dependencies,
    original_estimator_has_callable,
    transform_snowml_obj_to_sklearn_obj,
    validate_sklearn_args,
)
from snowflake.ml.modeling._internal.model_trainer_builder import ModelTrainerBuilder
from snowflake.ml.modeling._internal.snowpark_implementations.snowpark_handlers import (
    SnowparkHandlers as HandlersImpl,
)
from snowflake.ml.modeling.framework.base import BaseTransformer
from snowflake.snowpark import DataFrame
from snowflake.snowpark._internal.type_utils import convert_sp_to_sf_type

_PROJECT = "ModelDevelopment"
# Derive subproject from module name by removing "sklearn"
# and converting module name from underscore to CamelCase
# e.g. sklearn.linear_model -> LinearModel.
_SUBPROJECT = "ModelSelection"
DEFAULT_UDTF_NJOBS = 3


class GridSearchCV(BaseTransformer):
    r"""Exhaustive search over specified parameter values for an estimator
    For more details on this class, see [sklearn.model_selection.GridSearchCV]
    (https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GridSearchCV.html)

    Parameters
    ----------
    estimator: estimator object
        This is assumed to implement the scikit-learn estimator interface.
        Either estimator needs to provide a ``score`` function,
        or ``scoring`` must be passed.

    param_grid: dict or list of dictionaries
        Dictionary with parameters names (`str`) as keys and lists of
        parameter settings to try as values, or a list of such
        dictionaries, in which case the grids spanned by each dictionary
        in the list are explored. This enables searching over any sequence
        of parameter settings.

    input_cols: Optional[Union[str, List[str]]]
        A string or list of strings representing column names that contain features.
        If this parameter is not specified, all columns in the input DataFrame except
        the columns specified by label_cols and sample-weight_col parameters are
        considered input columns.

    label_cols: Optional[Union[str, List[str]]]
        A string or list of strings representing column names that contain labels.
        This is a required param for estimators, as there is no way to infer these
        columns. If this parameter is not specified, then object is fitted without
        labels(Like a transformer).

    output_cols: Optional[Union[str, List[str]]]
        A string or list of strings representing column names that will store the
        output of predict and transform operations. The length of output_cols mus
        match the expected number of output columns from the specific estimator or
        transformer class used.
        If this parameter is not specified, output column names are derived by
        adding an OUTPUT_ prefix to the label column names. These inferred output
        column names work for estimator's predict() method, but output_cols must
        be set explicitly for transformers.

    passthrough_cols: A string or a list of strings indicating column names to be excluded from any
        operations (such as train, transform, or inference). These specified column(s)
        will remain untouched throughout the process. This option is helpful in scenarios
        requiring automatic input_cols inference, but need to avoid using specific
        columns, like index columns, during training or inference.

    sample_weight_col: Optional[str]
        A string representing the column name containing the examples’ weights.
        This argument is only required when working with weighted datasets.

    drop_input_cols: Optional[bool], default=False
        If set, the response of predict(), transform() methods will not contain input columns.

    scoring: str, callable, list, tuple or dict, default=None
        Strategy to evaluate the performance of the cross-validated model on
        the test set.

        If `scoring` represents a single score, one can use:

        - a single string (see :ref:`scoring_parameter`);
        - a callable (see :ref:`scoring`) that returns a single value.

        If `scoring` represents multiple scores, one can use:

        - a list or tuple of unique strings;
        - a callable returning a dictionary where the keys are the metric
          names and the values are the metric scores;
        - a dictionary with metric names as keys and callables a values.

        See :ref:`multimetric_grid_search` for an example.

    n_jobs: int, default=None
        Number of jobs to run in parallel.
        ``None`` means 1 unless in a :obj:`joblib.parallel_backend` context.
        ``-1`` means using all processors. See :term:`Glossary <n_jobs>`
        for more details.

    refit: bool, str, or callable, default=True
        Refit an estimator using the best found parameters on the whole
        dataset.

        For multiple metric evaluation, this needs to be a `str` denoting the
        scorer that would be used to find the best parameters for refitting
        the estimator at the end.

        Where there are considerations other than maximum score in
        choosing a best estimator, ``refit`` can be set to a function which
        returns the selected ``best_index_`` given ``cv_results_``. In that
        case, the ``best_estimator_`` and ``best_params_`` will be set
        according to the returned ``best_index_`` while the ``best_score_``
        attribute will not be available.

        The refitted estimator is made available at the ``best_estimator_``
        attribute and permits using ``predict`` directly on this
        ``GridSearchCV`` instance.

        Also for multiple metric evaluation, the attributes ``best_index_``,
        ``best_score_`` and ``best_params_`` will only be available if
        ``refit`` is set and all of them will be determined w.r.t this specific
        scorer.

        See ``scoring`` parameter to know more about multiple metric
        evaluation.

        See :ref:`sphx_glr_auto_examples_model_selection_plot_grid_search_digits.py`
        to see how to design a custom selection strategy using a callable
        via `refit`.

    cv: int, cross-validation generator or an iterable, default=None
        Determines the cross-validation splitting strategy.
        Possible inputs for cv are:

        - None, to use the default 5-fold cross validation,
        - integer, to specify the number of folds in a `(Stratified)KFold`,
        - :term:`CV splitter`,
        - An iterable yielding (train, test) splits as arrays of indices.

        For integer/None inputs, if the estimator is a classifier and ``y`` is
        either binary or multiclass, :class:`StratifiedKFold` is used. In all
        other cases, :class:`KFold` is used. These splitters are instantiated
        with `shuffle=False` so the splits will be the same across calls.

        Refer :ref:`User Guide <cross_validation>` for the various
        cross-validation strategies that can be used here.

    verbose: int
        Controls the verbosity: the higher, the more messages.

        - >1 : the computation time for each fold and parameter candidate is
          displayed;
        - >2 : the score is also displayed;
        - >3 : the fold and candidate parameter indexes are also displayed
          together with the starting time of the computation.

    pre_dispatch: int, or str, default='2*n_jobs'
        Controls the number of jobs that get dispatched during parallel
        execution. Reducing this number can be useful to avoid an
        explosion of memory consumption when more jobs get dispatched
        than CPUs can process. This parameter can be:

            - None, in which case all the jobs are immediately
              created and spawned. Use this for lightweight and
              fast-running jobs, to avoid delays due to on-demand
              spawning of the jobs

            - An int, giving the exact number of total jobs that are
              spawned

            - A str, giving an expression as a function of n_jobs,
              as in '2*n_jobs'

    error_score: 'raise' or numeric, default=np.nan
        Value to assign to the score if an error occurs in estimator fitting.
        If set to 'raise', the error is raised. If a numeric value is given,
        FitFailedWarning is raised. This parameter does not affect the refit
        step, which will always raise the error.

    return_train_score: bool, default=False
        If ``False``, the ``cv_results_`` attribute will not include training
        scores.
        Computing training scores is used to get insights on how different
        parameter settings impact the overfitting/underfitting trade-off.
        However computing the scores on the training set can be computationally
        expensive and is not strictly required to select the parameters that
        yield the best generalization performance.
    """
    _ENABLE_DISTRIBUTED = True

    def __init__(  # type: ignore[no-untyped-def]
        self,
        *,
        estimator,
        param_grid,
        scoring=None,
        n_jobs=None,
        refit=True,
        cv=None,
        verbose=0,
        pre_dispatch="2*n_jobs",
        error_score=np.nan,
        return_train_score=False,
        input_cols: Optional[Union[str, Iterable[str]]] = None,
        output_cols: Optional[Union[str, Iterable[str]]] = None,
        label_cols: Optional[Union[str, Iterable[str]]] = None,
        passthrough_cols: Optional[Union[str, Iterable[str]]] = None,
        drop_input_cols: Optional[bool] = False,
        sample_weight_col: Optional[str] = None,
    ) -> None:
        super().__init__()
        deps: Set[str] = {
            f"numpy=={np.__version__}",
            f"scikit-learn=={sklearn.__version__}",
            f"cloudpickle=={cp.__version__}",
        }
        deps = deps | gather_dependencies(estimator)
        self._deps = list(deps)
        estimator = transform_snowml_obj_to_sklearn_obj(estimator)
        init_args = {
            "estimator": (estimator, None, True),
            "param_grid": (param_grid, None, True),
            "scoring": (scoring, None, False),
            "n_jobs": (n_jobs, None, False),
            "refit": (refit, True, False),
            "cv": (cv, None, False),
            "verbose": (verbose, 0, False),
            "pre_dispatch": (pre_dispatch, "2*n_jobs", False),
            "error_score": (error_score, np.nan, False),
            "return_train_score": (return_train_score, False, False),
        }
        cleaned_up_init_args = validate_sklearn_args(args=init_args, klass=sklearn.model_selection.GridSearchCV)
        self._sklearn_object: Any = sklearn.model_selection.GridSearchCV(
            **cleaned_up_init_args,
        )
        self._model_signature_dict: Optional[Dict[str, ModelSignature]] = None
        self.set_input_cols(input_cols)
        self.set_output_cols(output_cols)
        self.set_label_cols(label_cols)
        self.set_drop_input_cols(drop_input_cols)
        self.set_sample_weight_col(sample_weight_col)
        self.set_passthrough_cols(passthrough_cols)
        self._handlers: TransformerHandlers = HandlersImpl(
            class_name=self.__class__.__name__,
            subproject=_SUBPROJECT,
        )

    def _get_active_columns(self) -> List[str]:
        """ "Get the list of columns that are relevant to the transformer."""
        selected_cols = (
            self.input_cols + self.label_cols + ([self.sample_weight_col] if self.sample_weight_col is not None else [])
        )
        return selected_cols

    @telemetry.send_api_usage_telemetry(
        project=_PROJECT,
        subproject=_SUBPROJECT,
    )
    def fit(self, dataset: Union[DataFrame, pd.DataFrame]) -> "GridSearchCV":
        """Run fit with all sets of parameters
        For more details on this function, see [sklearn.model_selection.GridSearchCV.fit]
        (https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GridSearchCV.html#sklearn.model_selection.GridSearchCV.fit)

        Args:
            dataset: Union[snowflake.snowpark.DataFrame, pandas.DataFrame]
                Snowpark or Pandas DataFrame.

        Returns:
            self
        """
        self._infer_input_output_cols(dataset)
        if self._sklearn_object.n_jobs is None:
            self._sklearn_object.n_jobs = -1
        if isinstance(dataset, DataFrame):
            session = dataset._session
            assert session is not None  # keep mypy happy
            # Validate that key package version in user workspace are supported in snowflake conda channel
            # If customer doesn't have package in conda channel, replace the ones have the closest versions
            self._deps = pkg_version_utils.get_valid_pkg_versions_supported_in_snowflake_conda_channel(
                pkg_versions=self._get_dependencies(), session=session, subproject=_SUBPROJECT
            )

            # Specify input columns so column pruning will be enforced
            selected_cols = self._get_active_columns()
            if len(selected_cols) > 0:
                dataset = dataset.select(selected_cols)

            self._snowpark_cols = dataset.select(self.input_cols).columns

        model_trainer = ModelTrainerBuilder.build(
            estimator=self._sklearn_object,
            dataset=dataset,
            input_cols=self.input_cols,
            label_cols=self.label_cols,
            sample_weight_col=self.sample_weight_col,
            autogenerated=False,
            subproject=_SUBPROJECT,
        )
        self._sklearn_object = model_trainer.train()
        self._is_fitted = True
        self._get_model_signatures(dataset)
        return self

    def _get_pass_through_columns(self, dataset: DataFrame) -> List[str]:
        if self._drop_input_cols:
            return []
        else:
            return list(set(dataset.columns) - set(self.output_cols))

    def _batch_inference(
        self,
        dataset: DataFrame,
        inference_method: str,
        expected_output_cols_list: List[str],
        expected_output_cols_type: str = "",
    ) -> DataFrame:
        """Util method to create UDF and run batch inference."""
        if not self._is_fitted:
            raise exceptions.SnowflakeMLException(
                error_code=error_codes.METHOD_NOT_ALLOWED,
                original_exception=RuntimeError(
                    f"Estimator {self.__class__.__name__} not fitted before calling {inference_method} method."
                ),
            )

        session = dataset._session
        if session is None:
            raise exceptions.SnowflakeMLException(
                error_code=error_codes.NOT_FOUND,
                original_exception=ValueError("Session must not specified for snowpark dataset."),
            )
        # Validate that key package version in user workspace are supported in snowflake conda channel
        pkg_version_utils.get_valid_pkg_versions_supported_in_snowflake_conda_channel(
            pkg_versions=self._get_dependencies(), session=session, subproject=_SUBPROJECT
        )

        return self._handlers.batch_inference(
            dataset,
            session,
            self._sklearn_object,
            self._get_dependencies(),
            inference_method,
            self.input_cols,
            self._get_pass_through_columns(dataset),
            expected_output_cols_list,
            expected_output_cols_type,
        )

    def _sklearn_inference(
        self, dataset: pd.DataFrame, inference_method: str, expected_output_cols_list: List[str]
    ) -> pd.DataFrame:
        output_cols = expected_output_cols_list.copy()

        # Model expects exact same columns names in the input df for predict call.
        # Given the scenario that user use snowpark DataFrame in fit call, but pandas DataFrame in predict call
        # input cols need to match unquoted / quoted
        input_cols = self.input_cols
        unquoted_input_cols = identifier.get_unescaped_names(self.input_cols)
        quoted_input_cols = identifier.get_inferred_names(unquoted_input_cols)

        estimator = self._sklearn_object

        assert estimator is not None
        features_required_by_estimator = (
            estimator.feature_names_in_ if hasattr(estimator, "feature_names_in_") else unquoted_input_cols
        )
        missing_features = []
        features_in_dataset = set(dataset.columns)
        columns_to_select = []
        for i, f in enumerate(features_required_by_estimator):
            if (
                i >= len(input_cols)
                or (input_cols[i] != f and unquoted_input_cols[i] != f and quoted_input_cols[i] != f)
                or (
                    input_cols[i] not in features_in_dataset
                    and unquoted_input_cols[i] not in features_in_dataset
                    and quoted_input_cols[i] not in features_in_dataset
                )
            ):
                missing_features.append(f)
            elif input_cols[i] in features_in_dataset:
                columns_to_select.append(input_cols[i])
            elif unquoted_input_cols[i] in features_in_dataset:
                columns_to_select.append(unquoted_input_cols[i])
            else:
                columns_to_select.append(quoted_input_cols[i])

        if len(missing_features) > 0:
            raise exceptions.SnowflakeMLException(
                error_code=error_codes.NOT_FOUND,
                original_exception=ValueError(
                    "The feature names should match with those that were passed during fit.\n"
                    f"Features seen during fit call but not present in the input: {missing_features}\n"
                    f"Features in the input dataframe : {input_cols}\n"
                ),
            )
        input_df = dataset[columns_to_select]
        input_df.columns = features_required_by_estimator

        transformed_numpy_array = getattr(estimator, inference_method)(input_df)

        if (
            isinstance(transformed_numpy_array, list)
            and len(transformed_numpy_array) > 0
            and isinstance(transformed_numpy_array[0], np.ndarray)
        ):
            # In case of multioutput estimators, predict_proba(), decision_function(), etc., functions return
            # a list of ndarrays. We need to concatenate them.

            # First compute output column names
            if len(output_cols) == len(transformed_numpy_array):
                actual_output_cols = []
                for idx, np_arr in enumerate(transformed_numpy_array):
                    for i in range(1 if len(np_arr.shape) <= 1 else np_arr.shape[1]):
                        actual_output_cols.append(f"{output_cols[idx]}_{i}")
                output_cols = actual_output_cols

            # Concatenate np arrays
            transformed_numpy_array = np.concatenate(transformed_numpy_array, axis=1)

        if len(transformed_numpy_array.shape) == 3:
            # VotingClassifier will return results of shape (n_classifiers, n_samples, n_classes)
            # when voting = "soft" and flatten_transform = False. We can't handle unflatten transforms,
            # so we ignore flatten_transform flag and flatten the results.
            transformed_numpy_array = np.hstack(transformed_numpy_array)

        if len(transformed_numpy_array.shape) == 1:
            transformed_numpy_array = np.reshape(transformed_numpy_array, (-1, 1))

        shape = transformed_numpy_array.shape
        if shape[1] != len(output_cols):
            if len(output_cols) != 1:
                raise exceptions.SnowflakeMLException(
                    error_code=error_codes.INVALID_ARGUMENT,
                    original_exception=TypeError(
                        "expected_output_cols_list must be same length as transformed array or " "should be of length 1"
                    ),
                )
            actual_output_cols = []
            for i in range(shape[1]):
                actual_output_cols.append(f"{output_cols[0]}_{i}")
            output_cols = actual_output_cols

        if self._drop_input_cols:
            dataset = pd.DataFrame(data=transformed_numpy_array, columns=output_cols)
        else:
            dataset = dataset.copy()
            dataset[output_cols] = transformed_numpy_array
        return dataset

    @available_if(original_estimator_has_callable("predict"))  # type: ignore[misc]
    @telemetry.send_api_usage_telemetry(
        project=_PROJECT,
        subproject=_SUBPROJECT,
    )
    def predict(self, dataset: Union[DataFrame, pd.DataFrame]) -> Union[DataFrame, pd.DataFrame]:
        """Call predict on the estimator with the best found parameters
        For more details on this function, see [sklearn.model_selection.GridSearchCV.predict]
        (https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GridSearchCV.html#sklearn.model_selection.GridSearchCV.predict)


        Args:
            dataset: Union[snowflake.snowpark.DataFrame, pandas.DataFrame]
                Snowpark or Pandas DataFrame.

        Returns:
            Transformed dataset.
        """
        super()._check_dataset_type(dataset)
        if isinstance(dataset, DataFrame):
            expected_type_inferred = ""
            # infer the datatype from label columns
            if "predict" in self.model_signatures:
                expected_type_inferred = convert_sp_to_sf_type(
                    self.model_signatures["predict"].outputs[0].as_snowpark_type()
                )

            output_df = self._batch_inference(
                dataset=dataset,
                inference_method="predict",
                expected_output_cols_list=self.output_cols,
                expected_output_cols_type=expected_type_inferred,
            )
        elif isinstance(dataset, pd.DataFrame):
            output_df = self._sklearn_inference(
                dataset=dataset,
                inference_method="predict",
                expected_output_cols_list=self.output_cols,
            )

        return output_df

    @available_if(original_estimator_has_callable("transform"))  # type: ignore[misc]
    @telemetry.send_api_usage_telemetry(
        project=_PROJECT,
        subproject=_SUBPROJECT,
    )
    def transform(self, dataset: Union[DataFrame, pd.DataFrame]) -> Union[DataFrame, pd.DataFrame]:
        """Call transform on the estimator with the best found parameters
        For more details on this function, see [sklearn.model_selection.GridSearchCV.transform]
        (https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GridSearchCV.html#sklearn.model_selection.GridSearchCV.transform)

        Args:
            dataset: Union[snowflake.snowpark.DataFrame, pandas.DataFrame]
                Snowpark or Pandas DataFrame.

        Returns:
            Transformed dataset.
        """
        super()._check_dataset_type(dataset)
        if isinstance(dataset, DataFrame):
            output_df = self._batch_inference(
                dataset=dataset,
                inference_method="transform",
                expected_output_cols_list=self.output_cols,
            )
        elif isinstance(dataset, pd.DataFrame):
            output_df = self._sklearn_inference(
                dataset=dataset,
                inference_method="transform",
                expected_output_cols_list=self.output_cols,
            )

        return output_df

    def _get_output_column_names(self, output_cols_prefix: str) -> List[str]:
        """Returns the list of output columns for predict_proba(), decision_function(), etc.. functions.
        Returns a list with output_cols_prefix as the only element if the estimator is not a classifier.

        Args:
            output_cols_prefix (str): prefix according to the function

        Returns:
            List[str]: output cols with prefix
        """
        if getattr(self._sklearn_object, "classes_", None) is None:
            return [output_cols_prefix]

        assert self._sklearn_object is not None  # keep mypy happy
        classes = self._sklearn_object.classes_
        if isinstance(classes, np.ndarray):
            return [f"{output_cols_prefix}{c}" for c in classes.tolist()]
        elif isinstance(classes, list) and len(classes) > 0 and isinstance(classes[0], np.ndarray):
            # If the estimator is a multioutput estimator, classes_ will be a list of ndarrays.
            output_cols = []
            for i, cl in enumerate(classes):
                # For binary classification, there is only one output column for each class
                # ndarray as the two classes are complementary.
                if len(cl) == 2:
                    output_cols.append(f"{output_cols_prefix}_{i}_{cl[0]}")
                else:
                    output_cols.extend([f"{output_cols_prefix}_{i}_{c}" for c in cl.tolist()])
            return output_cols
        return []

    @available_if(original_estimator_has_callable("predict_proba"))  # type: ignore[misc]
    @telemetry.send_api_usage_telemetry(
        project=_PROJECT,
        subproject=_SUBPROJECT,
    )
    def predict_proba(
        self, dataset: Union[DataFrame, pd.DataFrame], output_cols_prefix: str = "predict_proba_"
    ) -> Union[DataFrame, pd.DataFrame]:
        """Call predict_proba on the estimator with the best found parameters
        For more details on this function, see [sklearn.model_selection.GridSearchCV.predict_proba]
        (https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GridSearchCV.html#sklearn.model_selection.GridSearchCV.predict_proba)

        Args:
            dataset: Union[snowflake.snowpark.DataFrame, pandas.DataFrame]
                Snowpark or Pandas DataFrame.
            output_cols_prefix: Prefix for the response columns

        Returns:
            Output dataset with probability of the sample for each class in the model.
        """
        super()._check_dataset_type(dataset)
        if isinstance(dataset, DataFrame):
            output_df = self._batch_inference(
                dataset=dataset,
                inference_method="predict_proba",
                expected_output_cols_list=self._get_output_column_names(output_cols_prefix),
                expected_output_cols_type="float",
            )
        elif isinstance(dataset, pd.DataFrame):
            output_df = self._sklearn_inference(
                dataset=dataset,
                inference_method="predict_proba",
                expected_output_cols_list=self._get_output_column_names(output_cols_prefix),
            )

        return output_df

    @available_if(original_estimator_has_callable("predict_log_proba"))  # type: ignore[misc]
    @telemetry.send_api_usage_telemetry(
        project=_PROJECT,
        subproject=_SUBPROJECT,
    )
    def predict_log_proba(
        self, dataset: Union[DataFrame, pd.DataFrame], output_cols_prefix: str = "predict_log_proba_"
    ) -> Union[DataFrame, pd.DataFrame]:
        """Call predict_proba on the estimator with the best found parameters
        For more details on this function, see [sklearn.model_selection.GridSearchCV.predict_proba]
        (https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GridSearchCV.html#sklearn.model_selection.GridSearchCV.predict_proba)

        Args:
            dataset: Union[snowflake.snowpark.DataFrame, pandas.DataFrame]
                Snowpark or Pandas DataFrame.
            output_cols_prefix: str
                Prefix for the response columns

        Returns:
            Output dataset with log probability of the sample for each class in the model.
        """
        super()._check_dataset_type(dataset)
        if isinstance(dataset, DataFrame):
            output_df = self._batch_inference(
                dataset=dataset,
                inference_method="predict_log_proba",
                expected_output_cols_list=self._get_output_column_names(output_cols_prefix),
                expected_output_cols_type="float",
            )
        elif isinstance(dataset, pd.DataFrame):
            output_df = self._sklearn_inference(
                dataset=dataset,
                inference_method="predict_log_proba",
                expected_output_cols_list=self._get_output_column_names(output_cols_prefix),
            )

        return output_df

    @available_if(original_estimator_has_callable("decision_function"))  # type: ignore[misc]
    @telemetry.send_api_usage_telemetry(
        project=_PROJECT,
        subproject=_SUBPROJECT,
    )
    def decision_function(
        self, dataset: Union[DataFrame, pd.DataFrame], output_cols_prefix: str = "decision_function_"
    ) -> Union[DataFrame, pd.DataFrame]:
        """Call decision_function on the estimator with the best found parameters
        For more details on this function, see [sklearn.model_selection.GridSearchCV.decision_function]
        (https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GridSearchCV.html#sklearn.model_selection.GridSearchCV.decision_function)

        Args:
            dataset: Union[snowflake.snowpark.DataFrame, pandas.DataFrame]
                Snowpark or Pandas DataFrame.
            output_cols_prefix: str
                Prefix for the response columns

        Returns:
            Output dataset with results of the decision function for the samples in input dataset.
        """
        super()._check_dataset_type(dataset)
        if isinstance(dataset, DataFrame):
            output_df = self._batch_inference(
                dataset=dataset,
                inference_method="decision_function",
                expected_output_cols_list=self._get_output_column_names(output_cols_prefix),
                expected_output_cols_type="float",
            )
        elif isinstance(dataset, pd.DataFrame):
            output_df = self._sklearn_inference(
                dataset=dataset,
                inference_method="decision_function",
                expected_output_cols_list=self._get_output_column_names(output_cols_prefix),
            )

        return output_df

    @available_if(original_estimator_has_callable("score"))  # type: ignore[misc]
    def score(self, dataset: Union[DataFrame, pd.DataFrame]) -> float:
        """
        If implemented by the original estimator, return the score for the dataset.

        Args:
            dataset: Union[snowflake.snowpark.DataFrame, pandas.DataFrame]
                Snowpark or Pandas DataFrame.

        Returns:
            Score.
        """
        self._infer_input_output_cols(dataset)
        super()._check_dataset_type(dataset)
        if isinstance(dataset, pd.DataFrame):
            output_score = self._handlers.score_pandas(
                dataset, self._sklearn_object, self.input_cols, self.label_cols, self.sample_weight_col
            )
        elif isinstance(dataset, DataFrame):
            output_score = self._score_snowpark(dataset)
        return output_score

    def _score_snowpark(self, dataset: DataFrame) -> float:
        # Specify input columns so column pruning will be enforced
        selected_cols = self._get_active_columns()
        if len(selected_cols) > 0:
            dataset = dataset.select(selected_cols)

        session = dataset._session
        assert session is not None  # keep mypy happy

        score = self._handlers.score_snowpark(
            dataset,
            session,
            self._sklearn_object,
            ["snowflake-snowpark-python"] + self._get_dependencies(),
            ["sklearn"],
            identifier.get_unescaped_names(self.input_cols),
            identifier.get_unescaped_names(self.label_cols),
            identifier.get_unescaped_names(self.sample_weight_col),
        )

        return score

    def _get_model_signatures(self, dataset: Union[DataFrame, pd.DataFrame]) -> None:
        self._model_signature_dict = dict()

        PROB_FUNCTIONS = ["predict_log_proba", "predict_proba", "decision_function"]

        inputs = list(_infer_signature(dataset[self.input_cols], "input"))
        outputs: List[BaseFeatureSpec] = []
        if hasattr(self, "predict"):
            # keep mypy happy
            assert self._sklearn_object is not None and hasattr(self._sklearn_object, "_estimator_type")
            # For classifier, the type of predict is the same as the type of label
            if self._sklearn_object._estimator_type == "classifier":
                # label columns is the desired type for output
                outputs = list(_infer_signature(dataset[self.label_cols], "output"))
                # rename the output columns
                outputs = list(model_signature_utils.rename_features(outputs, self.output_cols))
                self._model_signature_dict["predict"] = ModelSignature(
                    inputs, ([] if self._drop_input_cols else inputs) + outputs
                )
            # For regressor, the type of predict is float64
            elif self._sklearn_object._estimator_type == "regressor":
                outputs = [FeatureSpec(dtype=DataType.DOUBLE, name=c) for c in self.output_cols]
                self._model_signature_dict["predict"] = ModelSignature(
                    inputs, ([] if self._drop_input_cols else inputs) + outputs
                )
        for prob_func in PROB_FUNCTIONS:
            if hasattr(self, prob_func):
                output_cols_prefix: str = f"{prob_func}_"
                output_column_names = self._get_output_column_names(output_cols_prefix)
                outputs = [FeatureSpec(dtype=DataType.DOUBLE, name=c) for c in output_column_names]
                self._model_signature_dict[prob_func] = ModelSignature(
                    inputs, ([] if self._drop_input_cols else inputs) + outputs
                )

    @property
    def model_signatures(self) -> Dict[str, ModelSignature]:
        """Returns model signature of current class.

        Raises:
            SnowflakeMLException: If estimator is not fitted, then model signature cannot be inferred

        Returns:
            Dict[str, ModelSignature]: each method and its input output signature
        """
        if self._model_signature_dict is None:
            raise exceptions.SnowflakeMLException(
                error_code=error_codes.INVALID_ATTRIBUTE,
                original_exception=RuntimeError("Estimator not fitted before accessing property model_signatures!"),
            )
        return self._model_signature_dict

    def to_sklearn(self) -> sklearn.model_selection.GridSearchCV:
        """
        Get sklearn.model_selection.GridSearchCV object.
        """
        assert self._sklearn_object is not None
        return self._sklearn_object

    def _get_dependencies(self) -> List[str]:
        return self._deps
