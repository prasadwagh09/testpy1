import os
import tempfile
import warnings

import numpy as np
import pandas as pd
import xgboost
from absl.testing import absltest
from sklearn import datasets, model_selection

from snowflake.ml.model import model_signature
from snowflake.ml.model._packager import model_packager


class XgboostHandlerTest(absltest.TestCase):
    def test_xgb_booster(self) -> None:
        cal_data = datasets.load_breast_cancer()
        cal_X = pd.DataFrame(cal_data.data, columns=cal_data.feature_names)
        cal_y = pd.Series(cal_data.target)
        cal_X_train, cal_X_test, cal_y_train, cal_y_test = model_selection.train_test_split(cal_X, cal_y)
        params = dict(n_estimators=100, reg_lambda=1, gamma=0, max_depth=3, objective="binary:logistic")
        regressor = xgboost.train(params, xgboost.DMatrix(data=cal_X_train, label=cal_y_train))
        y_pred = regressor.predict(xgboost.DMatrix(data=cal_X_test))
        with tempfile.TemporaryDirectory() as tmpdir:
            s = {"predict": model_signature.infer_signature(cal_X_test, y_pred)}
            with self.assertRaises(ValueError):
                model_packager.ModelPackager(os.path.join(tmpdir, "model1")).save(
                    name="model1",
                    model=regressor,
                    signatures={**s, "another_predict": s["predict"]},
                    metadata={"author": "halu", "version": "1"},
                )

            model_packager.ModelPackager(os.path.join(tmpdir, "model1")).save(
                name="model1",
                model=regressor,
                signatures=s,
                metadata={"author": "halu", "version": "1"},
            )

            with warnings.catch_warnings():
                warnings.simplefilter("error")

                pk = model_packager.ModelPackager(os.path.join(tmpdir, "model1"))
                pk.load()
                assert pk.model
                assert pk.meta
                assert isinstance(pk.model, xgboost.Booster)
                np.testing.assert_allclose(pk.model.predict(xgboost.DMatrix(data=cal_X_test)), y_pred)
                pk = model_packager.ModelPackager(os.path.join(tmpdir, "model1"))
                pk.load(as_custom_model=True)
                assert pk.model
                assert pk.meta
                predict_method = getattr(pk.model, "predict", None)
                assert callable(predict_method)
                np.testing.assert_allclose(predict_method(cal_X_test), np.expand_dims(y_pred, axis=1))

            model_packager.ModelPackager(os.path.join(tmpdir, "model1_no_sig")).save(
                name="model1_no_sig",
                model=regressor,
                sample_input_data=cal_X_test,
                metadata={"author": "halu", "version": "1"},
            )

            pk = model_packager.ModelPackager(os.path.join(tmpdir, "model1_no_sig"))
            pk.load()
            assert pk.model
            assert pk.meta
            assert isinstance(pk.model, xgboost.Booster)
            np.testing.assert_allclose(pk.model.predict(xgboost.DMatrix(data=cal_X_test)), y_pred)
            self.assertEqual(s["predict"], pk.meta.signatures["predict"])

            pk = model_packager.ModelPackager(os.path.join(tmpdir, "model1_no_sig"))
            pk.load(as_custom_model=True)
            assert pk.model
            assert pk.meta
            predict_method = getattr(pk.model, "predict", None)
            assert callable(predict_method)
            np.testing.assert_allclose(predict_method(cal_X_test), np.expand_dims(y_pred, axis=1))

    def test_xgb(self) -> None:
        cal_data = datasets.load_breast_cancer()
        cal_X = pd.DataFrame(cal_data.data, columns=cal_data.feature_names)
        cal_y = pd.Series(cal_data.target)
        cal_X_train, cal_X_test, cal_y_train, cal_y_test = model_selection.train_test_split(cal_X, cal_y)
        regressor = xgboost.XGBClassifier(n_estimators=100, reg_lambda=1, gamma=0, max_depth=3)
        regressor.fit(cal_X_train, cal_y_train)
        y_pred = regressor.predict(cal_X_test)
        y_pred_proba = regressor.predict_proba(cal_X_test)
        with tempfile.TemporaryDirectory() as tmpdir:
            s = {"predict": model_signature.infer_signature(cal_X_test, y_pred)}
            with self.assertRaises(ValueError):
                model_packager.ModelPackager(os.path.join(tmpdir, "model1")).save(
                    name="model1",
                    model=regressor,
                    signatures={**s, "another_predict": s["predict"]},
                    metadata={"author": "halu", "version": "1"},
                )

            model_packager.ModelPackager(os.path.join(tmpdir, "model1")).save(
                name="model1",
                model=regressor,
                signatures=s,
                metadata={"author": "halu", "version": "1"},
            )

            with warnings.catch_warnings():
                warnings.simplefilter("error")

                pk = model_packager.ModelPackager(os.path.join(tmpdir, "model1"))
                pk.load()
                assert pk.model
                assert pk.meta
                assert isinstance(pk.model, xgboost.XGBClassifier)
                np.testing.assert_allclose(pk.model.predict(cal_X_test), y_pred)
                pk = model_packager.ModelPackager(os.path.join(tmpdir, "model1"))
                pk.load(as_custom_model=True)
                assert pk.model
                assert pk.meta
                predict_method = getattr(pk.model, "predict", None)
                assert callable(predict_method)
                np.testing.assert_allclose(predict_method(cal_X_test), np.expand_dims(y_pred, axis=1))

            model_packager.ModelPackager(os.path.join(tmpdir, "model1_no_sig")).save(
                name="model1_no_sig",
                model=regressor,
                sample_input_data=cal_X_test,
                metadata={"author": "halu", "version": "1"},
            )

            pk = model_packager.ModelPackager(os.path.join(tmpdir, "model1_no_sig"))
            pk.load()
            assert pk.model
            assert pk.meta
            assert isinstance(pk.model, xgboost.XGBClassifier)
            np.testing.assert_allclose(pk.model.predict(cal_X_test), y_pred)
            np.testing.assert_allclose(pk.model.predict_proba(cal_X_test), y_pred_proba)
            self.assertEqual(s["predict"], pk.meta.signatures["predict"])

            pk = model_packager.ModelPackager(os.path.join(tmpdir, "model1_no_sig"))
            pk.load(as_custom_model=True)
            assert pk.model
            assert pk.meta
            predict_method = getattr(pk.model, "predict", None)
            assert callable(predict_method)
            np.testing.assert_allclose(predict_method(cal_X_test), np.expand_dims(y_pred, axis=1))

            predict_method = getattr(pk.model, "predict_proba", None)
            assert callable(predict_method)
            np.testing.assert_allclose(predict_method(cal_X_test), y_pred_proba)


if __name__ == "__main__":
    absltest.main()
