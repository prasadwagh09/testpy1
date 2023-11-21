from typing import List, Tuple
from unittest import mock

import inflection
import numpy as np
import pandas as pd
from absl.testing import absltest, parameterized
from sklearn.datasets import load_iris
from sklearn.decomposition import PCA as SkPCA
from sklearn.ensemble import RandomForestClassifier as SkRandomForestClassifier
from sklearn.model_selection import GridSearchCV as SkGridSearchCV
from sklearn.svm import SVC as SkSVC, SVR as SkSVR
from xgboost import XGBClassifier as SkXGBClassifier

from snowflake.ml.modeling.decomposition import PCA
from snowflake.ml.modeling.ensemble import RandomForestClassifier
from snowflake.ml.modeling.model_selection._internal import GridSearchCV
from snowflake.ml.modeling.svm import SVC, SVR
from snowflake.ml.modeling.xgboost import XGBClassifier
from snowflake.ml.utils.connection_params import SnowflakeLoginOptions
from snowflake.snowpark import Session


def _load_iris_data() -> Tuple[pd.DataFrame, List[str], List[str]]:
    input_df_pandas = load_iris(as_frame=True).frame
    input_df_pandas.columns = [inflection.parameterize(c, "_").upper() for c in input_df_pandas.columns]
    input_df_pandas["INDEX"] = input_df_pandas.reset_index().index

    input_cols = [c for c in input_df_pandas.columns if not c.startswith("TARGET")]
    label_col = [c for c in input_df_pandas.columns if c.startswith("TARGET")]

    return input_df_pandas, input_cols, label_col


class GridSearchCVTest(parameterized.TestCase):
    def setUp(self):
        """Creates Snowpark and Snowflake environments for testing."""
        self._session = Session.builder.configs(SnowflakeLoginOptions()).create()

        pd_data, input_col, label_col = _load_iris_data()
        self._input_df_pandas = pd_data
        self._input_cols = input_col
        self._label_col = label_col
        self._input_df = self._session.create_dataframe(self._input_df_pandas)

    def tearDown(self):
        self._session.close()

    def _compare_cv_results(self, cv_result_1, cv_result_2) -> None:
        # compare the keys
        self.assertEqual(cv_result_1.keys(), cv_result_2.keys())
        # compare the values
        for k, v in cv_result_1.items():
            if isinstance(v, np.ndarray):
                if k.startswith("param_"):  # compare the masked array
                    np.ma.allequal(v, cv_result_2[k])
                elif k == "params":  # compare the parameter combination
                    self.assertEqual(v.tolist(), cv_result_2[k])
                elif k.endswith("test_score"):  # compare the test score
                    np.testing.assert_allclose(v, cv_result_2[k], rtol=1.0e-1, atol=1.0e-2)
                # Do not compare the fit time

    @mock.patch("snowflake.ml.modeling.model_selection._internal._grid_search_cv.is_single_node")
    def test_fit_and_compare_results(self, mock_is_single_node) -> None:
        mock_is_single_node.return_value = True  # falls back to HPO implementation

        sklearn_reg = SkGridSearchCV(estimator=SkSVR(), param_grid={"C": [1, 10], "kernel": ("linear", "rbf")})
        reg = GridSearchCV(estimator=SVR(), param_grid={"C": [1, 10], "kernel": ("linear", "rbf")})
        reg.set_input_cols(self._input_cols)
        output_cols = ["OUTPUT_" + c for c in self._label_col]
        reg.set_output_cols(output_cols)
        reg.set_label_cols(self._label_col)

        reg.fit(self._input_df)
        sklearn_reg.fit(X=self._input_df_pandas[self._input_cols], y=self._input_df_pandas[self._label_col].squeeze())

        actual_arr = reg.predict(self._input_df).to_pandas().sort_values(by="INDEX")[output_cols].to_numpy()
        sklearn_numpy_arr = sklearn_reg.predict(self._input_df_pandas[self._input_cols])

        # the result of SnowML grid search cv should behave the same as sklearn's
        assert reg._sklearn_object.best_params_ == sklearn_reg.best_params_
        np.testing.assert_allclose(reg._sklearn_object.best_score_, sklearn_reg.best_score_, rtol=1.0e-1, atol=1.0e-2)
        self._compare_cv_results(reg._sklearn_object.cv_results_, sklearn_reg.cv_results_)

        np.testing.assert_allclose(actual_arr.flatten(), sklearn_numpy_arr.flatten(), rtol=1.0e-1, atol=1.0e-2)

        # Test on fitting on snowpark Dataframe, and predict on pandas dataframe
        actual_arr_pd = reg.predict(self._input_df.to_pandas()).sort_values(by="INDEX")[output_cols].to_numpy()
        np.testing.assert_allclose(actual_arr_pd.flatten(), sklearn_numpy_arr.flatten(), rtol=1.0e-1, atol=1.0e-2)

    @parameterized.parameters(
        {
            "is_single_node": False,
            "skmodel": SkRandomForestClassifier,
            "model": RandomForestClassifier,
            "params": {"n_estimators": [50, 200], "min_samples_split": [1.0, 2, 3], "max_depth": [3, 8]},
            "kwargs": dict(),
            "estimator_kwargs": dict(random_state=0),
        },
        {
            "is_single_node": False,
            "skmodel": SkSVC,
            "model": SVC,
            "params": {"kernel": ("linear", "rbf"), "C": [1, 10, 80]},
            "kwargs": dict(),
            "estimator_kwargs": dict(random_state=0),
        },
        {
            "is_single_node": False,
            "skmodel": SkXGBClassifier,
            "model": XGBClassifier,
            "params": {"max_depth": [2, 6], "learning_rate": [0.1, 0.01]},
            "kwargs": dict(scoring=["accuracy", "f1_macro"], refit="f1_macro"),
            "estimator_kwargs": dict(seed=42),
        },
    )
    @mock.patch("snowflake.ml.modeling.model_selection._internal._grid_search_cv.is_single_node")
    def test_fit_and_compare_results_distributed(
        self, mock_is_single_node, is_single_node, skmodel, model, params, kwargs, estimator_kwargs
    ) -> None:
        mock_is_single_node.return_value = is_single_node

        sklearn_reg = SkGridSearchCV(estimator=skmodel(**estimator_kwargs), param_grid=params, cv=3, **kwargs)
        reg = GridSearchCV(estimator=model(**estimator_kwargs), param_grid=params, cv=3, **kwargs)
        reg.set_input_cols(self._input_cols)
        output_cols = ["OUTPUT_" + c for c in self._label_col]
        reg.set_output_cols(output_cols)
        reg.set_label_cols(self._label_col)

        reg.fit(self._input_df)
        sklearn_reg.fit(X=self._input_df_pandas[self._input_cols], y=self._input_df_pandas[self._label_col].squeeze())
        sk_obj = reg.to_sklearn()

        # the result of SnowML grid search cv should behave the same as sklearn's
        np.testing.assert_allclose(sk_obj.best_score_, sklearn_reg.best_score_)
        self.assertEqual(sk_obj.multimetric_, sklearn_reg.multimetric_)

        # self.assertEqual(sklearn_reg.multimetric_, False)
        self.assertEqual(sk_obj.best_index_, sklearn_reg.best_index_)
        self._compare_cv_results(sk_obj.cv_results_, sklearn_reg.cv_results_)

        if not sk_obj.multimetric_:
            self.assertEqual(sk_obj.best_params_, sklearn_reg.best_params_)

        actual_arr = reg.predict(self._input_df).to_pandas().sort_values(by="INDEX")[output_cols].to_numpy()
        sklearn_numpy_arr = sklearn_reg.predict(self._input_df_pandas[self._input_cols])
        np.testing.assert_allclose(actual_arr.flatten(), sklearn_numpy_arr.flatten(), rtol=1.0e-1, atol=1.0e-2)

        # Test on fitting on snowpark Dataframe, and predict on pandas dataframe
        actual_arr_pd = reg.predict(self._input_df.to_pandas()).sort_values(by="INDEX")[output_cols].to_numpy()
        np.testing.assert_allclose(actual_arr_pd.flatten(), sklearn_numpy_arr.flatten(), rtol=1.0e-1, atol=1.0e-2)

        # Test score
        actual_score = reg.score(self._input_df)
        sklearn_score = sklearn_reg.score(
            self._input_df_pandas[self._input_cols], self._input_df_pandas[self._label_col]
        )
        np.testing.assert_allclose(actual_score, sklearn_score, rtol=1.0e-1, atol=1.0e-2)

        # n_features_in_ is available because `refit` is set to `True`.
        self.assertEqual(sk_obj.n_features_in_, sklearn_reg.n_features_in_)

        # classes are available because these are classifier models
        for idx, class_ in enumerate(sk_obj.classes_):
            self.assertEqual(class_, sklearn_reg.classes_[idx])

        # Test predict_proba
        if hasattr(reg, "predict_proba"):
            actual_inference_result = (
                reg.predict_proba(self._input_df, output_cols_prefix="OUTPUT_").to_pandas().sort_values(by="INDEX")
            )
            actual_output_cols = [c for c in actual_inference_result.columns if c.find("OUTPUT_") >= 0]
            actual_inference_result = actual_inference_result[actual_output_cols].to_numpy()
            sklearn_predict_prob_array = sklearn_reg.predict_proba(self._input_df_pandas[self._input_cols])
            np.testing.assert_allclose(actual_inference_result.flatten(), sklearn_predict_prob_array.flatten())

        # Test predict_log_proba
        if hasattr(reg, "predict_log_proba"):
            actual_log_proba_result = (
                reg.predict_log_proba(self._input_df, output_cols_prefix="OUTPUT_").to_pandas().sort_values(by="INDEX")
            )
            actual_output_cols = [c for c in actual_log_proba_result.columns if c.find("OUTPUT_") >= 0]
            actual_log_proba_result = actual_log_proba_result[actual_output_cols].to_numpy()
            sklearn_log_prob_array = sklearn_reg.predict_log_proba(self._input_df_pandas[self._input_cols])
            np.testing.assert_allclose(actual_log_proba_result.flatten(), sklearn_log_prob_array.flatten())

        # Test decision function
        if hasattr(reg, "decision_function"):
            actual_decision_function = (
                reg.decision_function(self._input_df, output_cols_prefix="OUTPUT_").to_pandas().sort_values(by="INDEX")
            )
            actual_output_cols = [c for c in actual_decision_function.columns if c.find("OUTPUT_") >= 0]
            actual_decision_function_result = actual_decision_function[actual_output_cols].to_numpy()
            sklearn_decision_function = sklearn_reg.decision_function(self._input_df_pandas[self._input_cols])
            np.testing.assert_allclose(
                actual_decision_function_result, sklearn_decision_function, rtol=1.0e-1, atol=1.0e-2
            )

    @mock.patch("snowflake.ml.modeling.model_selection._internal._grid_search_cv.is_single_node")
    def test_transform(self, mock_is_single_node) -> None:
        mock_is_single_node.return_value = False

        params = {"n_components": range(1, 3)}
        sk_pca = SkPCA()
        sklearn_reg = SkGridSearchCV(sk_pca, params, cv=3)

        pca = PCA()
        reg = GridSearchCV(estimator=pca, param_grid=params, cv=3)
        reg.set_input_cols(self._input_cols)
        output_cols = ["OUTPUT_" + c for c in self._label_col]
        reg.set_output_cols(output_cols)
        reg.set_label_cols(self._label_col)

        reg.fit(self._input_df)
        sklearn_reg.fit(X=self._input_df_pandas[self._input_cols], y=self._input_df_pandas[self._label_col].squeeze())

        transformed = reg.transform(self._input_df).to_pandas().sort_values(by="INDEX")
        sk_transformed = sklearn_reg.transform(self._input_df_pandas[self._input_cols])

        actual_output_cols = [c for c in transformed.columns if c.find("OUTPUT_") >= 0]
        transformed = transformed[actual_output_cols].astype("float64").to_numpy()

        np.testing.assert_allclose(transformed, sk_transformed, rtol=1.0e-1, atol=1.0e-2)


if __name__ == "__main__":
    absltest.main()
