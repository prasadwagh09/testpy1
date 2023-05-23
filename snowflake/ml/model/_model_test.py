import asyncio
import os
import tempfile
import warnings

import numpy as np
import pandas as pd
import xgboost
from absl.testing import absltest
from sklearn import datasets, ensemble, linear_model, model_selection, multioutput

from snowflake.ml.model import (
    _model as model_api,
    custom_model,
    model_signature,
    type_hints as model_types,
)
from snowflake.ml.modeling.linear_model import LinearRegression


class DemoModelWithManyArtifacts(custom_model.CustomModel):
    def __init__(self, context: custom_model.ModelContext) -> None:
        super().__init__(context)
        with open(os.path.join(context.path("bias"), "bias1")) as f:
            v1 = int(f.read())
        with open(os.path.join(context.path("bias"), "bias2")) as f:
            v2 = int(f.read())
        self.bias = v1 + v2

    @custom_model.inference_api
    def predict(self, input: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"output": input["c1"] + self.bias})


class DemoModel(custom_model.CustomModel):
    def __init__(self, context: custom_model.ModelContext) -> None:
        super().__init__(context)

    @custom_model.inference_api
    def predict(self, input: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"output": input["c1"]})


class AnotherDemoModel(custom_model.CustomModel):
    def __init__(self, context: custom_model.ModelContext) -> None:
        super().__init__(context)

    @custom_model.inference_api
    def predict(self, input: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(input[["c1", "c2"]])


class ComposeModel(custom_model.CustomModel):
    def __init__(self, context: custom_model.ModelContext) -> None:
        super().__init__(context)

    @custom_model.inference_api
    def predict(self, input: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            (self.context.model_ref("m1").predict(input)["c1"] + self.context.model_ref("m2").predict(input)["output"])
            / 2,
            columns=["output"],
        )


class AsyncComposeModel(custom_model.CustomModel):
    def __init__(self, context: custom_model.ModelContext) -> None:
        super().__init__(context)

    @custom_model.inference_api
    async def predict(self, input: pd.DataFrame) -> pd.DataFrame:
        res1 = await self.context.model_ref("m1").predict.async_run(input)
        res_sum = res1["output"] + self.context.model_ref("m2").predict(input)["output"]
        return pd.DataFrame(res_sum / 2)


class DemoModelWithArtifacts(custom_model.CustomModel):
    def __init__(self, context: custom_model.ModelContext) -> None:
        super().__init__(context)
        with open(context.path("bias")) as f:
            v = int(f.read())
        self.bias = v

    @custom_model.inference_api
    def predict(self, input: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"output": input["c1"] + self.bias})


class ModelTest(absltest.TestCase):
    def test_bad_save_model(self) -> None:
        tmpdir = self.create_tempdir()
        os.mkdir(os.path.join(tmpdir.full_path, "bias"))
        with open(os.path.join(tmpdir.full_path, "bias", "bias1"), "w") as f:
            f.write("25")
        with open(os.path.join(tmpdir.full_path, "bias", "bias2"), "w") as f:
            f.write("68")
        lm = DemoModelWithManyArtifacts(
            custom_model.ModelContext(models={}, artifacts={"bias": os.path.join(tmpdir.full_path, "bias")})
        )
        arr = np.array([[1, 2, 3], [4, 2, 5]])
        d = pd.DataFrame(arr, columns=["c1", "c2", "c3"])
        s = {"predict": model_signature.infer_signature(d, lm.predict(d))}
        with self.assertRaises(ValueError):
            model_api.save_model(  # type:ignore[call-overload]
                name="model1",
                model_dir_path=os.path.join(tmpdir.full_path, "model1"),
                model=lm,
                signatures=s,
                sample_input=d,
                metadata={"author": "halu", "version": "1"},
            )

        with self.assertRaises(ValueError):
            model_api.save_model(
                name="model1",
                model_dir_path=os.path.join(tmpdir.full_path, "model1"),
                model=lm,
                signatures={**s, "another_predict": s["predict"]},
                metadata={"author": "halu", "version": "1"},
            )

        with self.assertRaises(ValueError):
            model_api.save_model(  # type:ignore[call-overload]
                name="model1",
                model_dir_path=os.path.join(tmpdir.full_path, "model1"),
                model=lm,
                metadata={"author": "halu", "version": "1"},
            )

    def test_custom_model_with_multiple_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.mkdir(os.path.join(tmpdir, "bias"))
            with open(os.path.join(tmpdir, "bias", "bias1"), "w") as f:
                f.write("25")
            with open(os.path.join(tmpdir, "bias", "bias2"), "w") as f:
                f.write("68")
            lm = DemoModelWithManyArtifacts(
                custom_model.ModelContext(
                    models={}, artifacts={"bias": os.path.join(tmpdir, "bias", "")}
                )  # Test sanitizing user path input.
            )
            arr = np.array([[1, 2, 3], [4, 2, 5]])
            d = pd.DataFrame(arr, columns=["c1", "c2", "c3"])
            s = {"predict": model_signature.infer_signature(d, lm.predict(d))}
            model_api.save_model(
                name="model1",
                model_dir_path=os.path.join(tmpdir, "model1"),
                model=lm,
                signatures=s,
                metadata={"author": "halu", "version": "1"},
            )
            with warnings.catch_warnings():
                warnings.simplefilter("error")

                m, meta = model_api.load_model(os.path.join(tmpdir, "model1"))
                assert isinstance(m, DemoModelWithManyArtifacts)
                res = m.predict(d)
                np.testing.assert_allclose(res["output"], pd.Series(np.array([94, 97])))

                m_UDF, meta = model_api._load_model_for_deploy(os.path.join(tmpdir, "model1"))
                assert isinstance(m_UDF, DemoModelWithManyArtifacts)
                res = m_UDF.predict(d)
                np.testing.assert_allclose(res["output"], pd.Series(np.array([94, 97])))
                self.assertEqual(meta.metadata["author"] if meta.metadata else None, "halu")

                model_api.save_model(
                    name="model1_no_sig",
                    model_dir_path=os.path.join(tmpdir, "model1_no_sig"),
                    model=lm,
                    sample_input=d,
                    metadata={"author": "halu", "version": "1"},
                )

                m, meta = model_api.load_model(os.path.join(tmpdir, "model1_no_sig"))
                assert isinstance(m, DemoModelWithManyArtifacts)
                res = m.predict(d)
                np.testing.assert_allclose(res["output"], pd.Series(np.array([94, 97])))
                self.assertEqual(s, meta.signatures)

    def test_model_composition(self) -> None:
        arr = np.array([[1, 2, 3], [4, 2, 5]])
        d = pd.DataFrame(arr, columns=["c1", "c2", "c3"])
        aclf = AnotherDemoModel(custom_model.ModelContext())
        clf = DemoModel(custom_model.ModelContext())
        model_context = custom_model.ModelContext(
            models={
                "m1": aclf,
                "m2": clf,
            }
        )
        acm = ComposeModel(model_context)
        p1 = clf.predict(d)
        p2 = acm.predict(d)
        s = {"predict": model_signature.infer_signature(d, p2)}
        with tempfile.TemporaryDirectory() as tmpdir:
            model_api.save_model(
                name="model1",
                model_dir_path=os.path.join(tmpdir, "model1"),
                model=acm,
                signatures=s,
                metadata={"author": "halu", "version": "1"},
            )
            lm, _ = model_api.load_model(os.path.join(tmpdir, "model1"))
            assert isinstance(lm, ComposeModel)
            p3 = lm.predict(d)

            m_UDF, _ = model_api._load_model_for_deploy(os.path.join(tmpdir, "model1"))
            assert isinstance(m_UDF, ComposeModel)
            p4 = m_UDF.predict(d)
            np.testing.assert_allclose(p1, p2)
            np.testing.assert_allclose(p2, p3)
            np.testing.assert_allclose(p2, p4)

    def test_async_model_composition(self) -> None:
        async def _test(self: "ModelTest") -> None:
            arr = np.array([[1, 2, 3], [4, 2, 5]])
            d = pd.DataFrame(arr, columns=["c1", "c2", "c3"])
            clf = DemoModel(custom_model.ModelContext())
            model_context = custom_model.ModelContext(
                models={
                    "m1": clf,
                    "m2": clf,
                }
            )
            acm = AsyncComposeModel(model_context)
            p1 = clf.predict(d)
            p2 = await acm.predict(d)
            s = {"predict": model_signature.infer_signature(d, p2)}
            with tempfile.TemporaryDirectory() as tmpdir:
                model_api.save_model(
                    name="model1",
                    model_dir_path=os.path.join(tmpdir, "model1"),
                    model=acm,
                    signatures=s,
                    metadata={"author": "halu", "version": "1"},
                )
                lm, _ = model_api.load_model(os.path.join(tmpdir, "model1"))
                assert isinstance(lm, AsyncComposeModel)
                p3 = await lm.predict(d)  # type: ignore[misc]

                m_UDF, _ = model_api._load_model_for_deploy(os.path.join(tmpdir, "model1"))
                assert isinstance(m_UDF, AsyncComposeModel)
                p4 = await m_UDF.predict(d)
                np.testing.assert_allclose(p1, p2)
                np.testing.assert_allclose(p2, p3)
                np.testing.assert_allclose(p2, p4)

        asyncio.get_event_loop().run_until_complete(_test(self))

    def test_custom_model_with_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "bias"), "w") as f:
                f.write("10")
            lm = DemoModelWithArtifacts(
                custom_model.ModelContext(models={}, artifacts={"bias": os.path.join(tmpdir, "bias")})
            )
            arr = np.array([[1, 2, 3], [4, 2, 5]])
            d = pd.DataFrame(arr, columns=["c1", "c2", "c3"])
            s = {"predict": model_signature.infer_signature(d, lm.predict(d))}
            model_api.save_model(
                name="model1",
                model_dir_path=os.path.join(tmpdir, "model1"),
                model=lm,
                signatures=s,
                metadata={"author": "halu", "version": "1"},
            )

            m, meta = model_api.load_model(os.path.join(tmpdir, "model1"))
            assert isinstance(m, DemoModelWithArtifacts)
            res = m.predict(d)
            np.testing.assert_allclose(res["output"], pd.Series(np.array([11, 14])))

            # test re-init when loading the model
            with open(os.path.join(tmpdir, "model1", "models", "model1", "artifacts", "bias"), "w") as f:
                f.write("20")

            m_UDF, meta = model_api._load_model_for_deploy(os.path.join(tmpdir, "model1"))
            assert isinstance(m_UDF, DemoModelWithArtifacts)
            res = m_UDF.predict(d)

            np.testing.assert_allclose(res["output"], pd.Series(np.array([21, 24])))
            self.assertEqual(meta.metadata["author"] if meta.metadata else None, "halu")

    def test_skl_multiple_output_proba(self) -> None:
        iris_X, iris_y = datasets.load_iris(return_X_y=True)
        target2 = np.random.randint(0, 6, size=iris_y.shape)
        dual_target = np.vstack([iris_y, target2]).T
        model = multioutput.MultiOutputClassifier(ensemble.RandomForestClassifier(random_state=42))
        iris_X_df = pd.DataFrame(iris_X, columns=["c1", "c2", "c3", "c4"])
        model.fit(iris_X_df[:-10], dual_target[:-10])
        with tempfile.TemporaryDirectory() as tmpdir:
            s = {"predict_proba": model_signature.infer_signature(iris_X_df, model.predict_proba(iris_X_df))}
            model_api.save_model(
                name="model1",
                model_dir_path=os.path.join(tmpdir, "model1"),
                model=model,
                signatures=s,
                metadata={"author": "halu", "version": "1"},
                conda_dependencies=["scikit-learn"],
            )

            m: multioutput.MultiOutputClassifier
            m, _ = model_api.load_model(os.path.join(tmpdir, "model1"))
            np.testing.assert_allclose(
                np.hstack(model.predict_proba(iris_X_df[-10:])), np.hstack(m.predict_proba(iris_X_df[-10:]))
            )

            m_udf, _ = model_api._load_model_for_deploy(os.path.join(tmpdir, "model1"))
            predict_method = getattr(m_udf, "predict_proba", None)
            assert callable(predict_method)
            np.testing.assert_allclose(np.hstack(model.predict_proba(iris_X_df[-10:])), predict_method(iris_X_df[-10:]))

            with self.assertRaises(ValueError):
                model_api.save_model(
                    name="model1_no_sig_bad",
                    model_dir_path=os.path.join(tmpdir, "model1_no_sig_bad"),
                    model=model,
                    sample_input=iris_X_df,
                    metadata={"author": "halu", "version": "1"},
                    options=model_types.SKLModelSaveOptions({"target_methods": ["random"]}),
                )

            model_api.save_model(
                name="model1_no_sig",
                model_dir_path=os.path.join(tmpdir, "model1_no_sig"),
                model=model,
                sample_input=iris_X_df,
                metadata={"author": "halu", "version": "1"},
            )

            m, meta = model_api.load_model(os.path.join(tmpdir, "model1_no_sig"))
            np.testing.assert_allclose(
                np.hstack(model.predict_proba(iris_X_df[-10:])), np.hstack(m.predict_proba(iris_X_df[-10:]))
            )
            np.testing.assert_allclose(model.predict(iris_X_df[-10:]), m.predict(iris_X_df[-10:]))
            self.assertEqual(s["predict_proba"], meta.signatures["predict_proba"])

            m_udf, _ = model_api._load_model_for_deploy(os.path.join(tmpdir, "model1_no_sig"))

            predict_method = getattr(m_udf, "predict_proba", None)
            assert callable(predict_method)
            np.testing.assert_allclose(np.hstack(model.predict_proba(iris_X_df[-10:])), predict_method(iris_X_df[-10:]))

            predict_method = getattr(m_udf, "predict", None)
            assert callable(predict_method)
            np.testing.assert_allclose(model.predict(iris_X_df[-10:]), predict_method(iris_X_df[-10:]))

    def test_skl(self) -> None:
        iris_X, iris_y = datasets.load_iris(return_X_y=True)
        regr = linear_model.LinearRegression()
        iris_X_df = pd.DataFrame(iris_X, columns=["c1", "c2", "c3", "c4"])
        regr.fit(iris_X_df, iris_y)
        with tempfile.TemporaryDirectory() as tmpdir:
            s = {"predict": model_signature.infer_signature(iris_X_df, regr.predict(iris_X_df))}
            with self.assertRaises(ValueError):
                model_api.save_model(
                    name="model1",
                    model_dir_path=os.path.join(tmpdir, "model1"),
                    model=regr,
                    signatures={**s, "another_predict": s["predict"]},
                    metadata={"author": "halu", "version": "1"},
                )

            model_api.save_model(
                name="model1",
                model_dir_path=os.path.join(tmpdir, "model1"),
                model=regr,
                signatures=s,
                metadata={"author": "halu", "version": "1"},
            )

            with warnings.catch_warnings():
                warnings.simplefilter("error")

                m: linear_model.LinearRegression
                m, _ = model_api.load_model(os.path.join(tmpdir, "model1"))
                np.testing.assert_allclose(np.array([-0.08254936]), m.predict(iris_X_df[:1]))
                m_udf, _ = model_api._load_model_for_deploy(os.path.join(tmpdir, "model1"))
                predict_method = getattr(m_udf, "predict", None)
                assert callable(predict_method)
                np.testing.assert_allclose(np.array([[-0.08254936]]), predict_method(iris_X_df[:1]))

            model_api.save_model(
                name="model1_no_sig",
                model_dir_path=os.path.join(tmpdir, "model1_no_sig"),
                model=regr,
                sample_input=iris_X_df,
                metadata={"author": "halu", "version": "1"},
            )

            m, meta = model_api.load_model(os.path.join(tmpdir, "model1_no_sig"))
            np.testing.assert_allclose(np.array([-0.08254936]), m.predict(iris_X_df[:1]))
            self.assertEqual(s["predict"], meta.signatures["predict"])

            m_udf, _ = model_api._load_model_for_deploy(os.path.join(tmpdir, "model1_no_sig"))
            predict_method = getattr(m_udf, "predict", None)
            assert callable(predict_method)
            np.testing.assert_allclose(np.array([[-0.08254936]]), predict_method(iris_X_df[:1]))

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
                model_api.save_model(
                    name="model1",
                    model_dir_path=os.path.join(tmpdir, "model1"),
                    model=regressor,
                    signatures={**s, "another_predict": s["predict"]},
                    metadata={"author": "halu", "version": "1"},
                )

            model_api.save_model(
                name="model1",
                model_dir_path=os.path.join(tmpdir, "model1"),
                model=regressor,
                signatures=s,
                metadata={"author": "halu", "version": "1"},
            )

            with warnings.catch_warnings():
                warnings.simplefilter("error")

                m, _ = model_api.load_model(os.path.join(tmpdir, "model1"))
                assert isinstance(m, xgboost.XGBClassifier)
                np.testing.assert_allclose(m.predict(cal_X_test), y_pred)
                m_udf, _ = model_api._load_model_for_deploy(os.path.join(tmpdir, "model1"))
                predict_method = getattr(m_udf, "predict", None)
                assert callable(predict_method)
                np.testing.assert_allclose(predict_method(cal_X_test), np.expand_dims(y_pred, axis=1))

            model_api.save_model(
                name="model1_no_sig",
                model_dir_path=os.path.join(tmpdir, "model1_no_sig"),
                model=regressor,
                sample_input=cal_X_test,
                metadata={"author": "halu", "version": "1"},
            )

            m, meta = model_api.load_model(os.path.join(tmpdir, "model1_no_sig"))
            assert isinstance(m, xgboost.XGBClassifier)
            np.testing.assert_allclose(m.predict(cal_X_test), y_pred)
            np.testing.assert_allclose(m.predict_proba(cal_X_test), y_pred_proba)
            self.assertEqual(s["predict"], meta.signatures["predict"])

            m_udf, _ = model_api._load_model_for_deploy(os.path.join(tmpdir, "model1_no_sig"))
            predict_method = getattr(m_udf, "predict", None)
            assert callable(predict_method)
            np.testing.assert_allclose(predict_method(cal_X_test), np.expand_dims(y_pred, axis=1))

            predict_method = getattr(m_udf, "predict_proba", None)
            assert callable(predict_method)
            np.testing.assert_allclose(predict_method(cal_X_test), y_pred_proba)

    def test_snowml(self) -> None:
        iris = datasets.load_iris()

        df = pd.DataFrame(data=np.c_[iris["data"], iris["target"]], columns=iris["feature_names"] + ["target"])
        df.columns = [s.replace(" (CM)", "").replace(" ", "") for s in df.columns.str.upper()]

        INPUT_COLUMNS = ["SEPALLENGTH", "SEPALWIDTH", "PETALLENGTH", "PETALWIDTH"]
        LABEL_COLUMNS = "TARGET"
        OUTPUT_COLUMNS = "PREDICTED_TARGET"
        regr = LinearRegression(input_cols=INPUT_COLUMNS, output_cols=OUTPUT_COLUMNS, label_cols=LABEL_COLUMNS)
        regr.fit(df)

        predictions = regr.predict(df[:1])[[OUTPUT_COLUMNS]]

        with tempfile.TemporaryDirectory() as tmpdir:
            s = {"predict": model_signature.infer_signature(df[INPUT_COLUMNS], regr.predict(df)[[OUTPUT_COLUMNS]])}
            with self.assertRaises(ValueError):
                model_api.save_model(
                    name="model1",
                    model_dir_path=os.path.join(tmpdir, "model1"),
                    model=regr,
                    signatures={**s, "another_predict": s["predict"]},
                    metadata={"author": "halu", "version": "1"},
                )

            model_api.save_model(
                name="model1",
                model_dir_path=os.path.join(tmpdir, "model1"),
                model=regr,
                signatures=s,
                metadata={"author": "halu", "version": "1"},
            )

            with warnings.catch_warnings():
                warnings.simplefilter("error")

                m: LinearRegression
                m, _ = model_api.load_model(os.path.join(tmpdir, "model1"))
                np.testing.assert_allclose(predictions, m.predict(df[:1])[[OUTPUT_COLUMNS]])
                m_udf, _ = model_api._load_model_for_deploy(os.path.join(tmpdir, "model1"))
                predict_method = getattr(m_udf, "predict", None)
                assert callable(predict_method)
                np.testing.assert_allclose(predictions, predict_method(df[:1])[[OUTPUT_COLUMNS]])

            model_api.save_model(
                name="model1_no_sig",
                model_dir_path=os.path.join(tmpdir, "model1_no_sig"),
                model=regr,
                sample_input=df,
                metadata={"author": "halu", "version": "1"},
            )

            m, meta = model_api.load_model(os.path.join(tmpdir, "model1_no_sig"))
            np.testing.assert_allclose(np.array([[-0.08254936]]), m.predict(df[:1])[[OUTPUT_COLUMNS]])
            # TODO: After model_signatures() function is updated in codegen, next line should be changed to
            # s = regr.model_signatures()
            # self.assertEqual(s["predict"], meta.signatures["predict"])

            m_udf, _ = model_api._load_model_for_deploy(os.path.join(tmpdir, "model1_no_sig"))
            predict_method = getattr(m_udf, "predict", None)
            assert callable(predict_method)
            np.testing.assert_allclose(np.array([[-0.08254936]]), predict_method(df[:1])[[OUTPUT_COLUMNS]])


if __name__ == "__main__":
    absltest.main()
