from typing import cast
from unittest import mock

import pandas as pd
from absl.testing import absltest

from snowflake.ml._internal.utils import sql_identifier
from snowflake.ml.model._client.model import model_impl, model_version_impl
from snowflake.ml.model._model_composer import model_composer
from snowflake.ml.registry._manager import model_manager
from snowflake.ml.test_utils import mock_session
from snowflake.snowpark import Row, Session


class RegistryTest(absltest.TestCase):
    def setUp(self) -> None:
        self.m_session = mock_session.MockSession(conn=None, test_case=self)
        self.c_session = cast(Session, self.m_session)
        self.m_r = model_manager.ModelManager(
            self.c_session,
            database_name=sql_identifier.SqlIdentifier("TEMP"),
            schema_name=sql_identifier.SqlIdentifier("TEST"),
        )

    def test_get_model_1(self) -> None:
        m_model = model_impl.Model._ref(
            self.m_r._model_ops,
            model_name=sql_identifier.SqlIdentifier("MODEL"),
        )
        with mock.patch.object(self.m_r._model_ops, "validate_existence", return_value=True) as mock_validate_existence:
            m = self.m_r.get_model("MODEL")
            self.assertEqual(m, m_model)
            mock_validate_existence.assert_called_once_with(
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                statement_params=mock.ANY,
            )

    def test_get_model_2(self) -> None:
        with mock.patch.object(
            self.m_r._model_ops, "validate_existence", return_value=False
        ) as mock_validate_existence:
            with self.assertRaisesRegex(ValueError, "Unable to find model MODEL"):
                self.m_r.get_model("MODEL")
            mock_validate_existence.assert_called_once_with(
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                statement_params=mock.ANY,
            )

    def test_models(self) -> None:
        m_model_1 = model_impl.Model._ref(
            self.m_r._model_ops,
            model_name=sql_identifier.SqlIdentifier("MODEL"),
        )
        m_model_2 = model_impl.Model._ref(
            self.m_r._model_ops,
            model_name=sql_identifier.SqlIdentifier("Model", case_sensitive=True),
        )
        with mock.patch.object(
            self.m_r._model_ops,
            "list_models_or_versions",
            return_value=[
                sql_identifier.SqlIdentifier("MODEL"),
                sql_identifier.SqlIdentifier("Model", case_sensitive=True),
            ],
        ) as mock_list_models_or_versions:
            m_list = self.m_r.models()
            self.assertListEqual(m_list, [m_model_1, m_model_2])
            mock_list_models_or_versions.assert_called_once_with(
                statement_params=mock.ANY,
            )

    def test_show_models(self) -> None:
        m_list_res = [
            Row(
                create_on="06/01",
                name="MODEL",
                comment="This is a comment",
                model_name="MODEL",
                database_name="TEMP",
                schema_name="test",
                default_version_name="V1",
            ),
            Row(
                create_on="06/01",
                name="Model",
                comment="This is a comment",
                model_name="MODEL",
                database_name="TEMP",
                schema_name="test",
                default_version_name="v1",
            ),
        ]
        with mock.patch.object(
            self.m_r._model_ops,
            "show_models_or_versions",
            return_value=m_list_res,
        ) as mock_show_models_or_versions:
            mv_info = self.m_r.show_models()
            pd.testing.assert_frame_equal(mv_info, pd.DataFrame([row.as_dict() for row in m_list_res]))
            mock_show_models_or_versions.assert_called_once_with(
                statement_params=mock.ANY,
            )

    def test_log_model_1(self) -> None:
        m_model = mock.MagicMock()
        m_conda_dependency = mock.MagicMock()
        m_sample_input_data = mock.MagicMock()
        m_stage_path = "@TEMP.TEST.MODEL/V1"
        with mock.patch.object(
            self.m_r._model_ops, "validate_existence", return_value=False
        ) as mock_validate_existence, mock.patch.object(
            self.m_r._model_ops, "prepare_model_stage_path", return_value=m_stage_path
        ) as mock_prepare_model_stage_path, mock.patch.object(
            model_composer.ModelComposer, "save"
        ) as mock_save, mock.patch.object(
            self.m_r._model_ops, "create_from_stage"
        ) as mock_create_from_stage:
            mv = self.m_r.log_model(
                model=m_model,
                model_name="MODEL",
                version_name="v1",
                conda_dependencies=m_conda_dependency,
                sample_input_data=m_sample_input_data,
            )
            mock_validate_existence.assert_called_once_with(
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                statement_params=mock.ANY,
            )
            mock_prepare_model_stage_path.assert_called_once_with(
                statement_params=mock.ANY,
            )
            mock_save.assert_called_once_with(
                name="MODEL",
                model=m_model,
                signatures=None,
                sample_input_data=m_sample_input_data,
                conda_dependencies=m_conda_dependency,
                pip_requirements=None,
                python_version=None,
                code_paths=None,
                ext_modules=None,
                options=None,
            )
            mock_create_from_stage.assert_called_once_with(
                composed_model=mock.ANY,
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                version_name=sql_identifier.SqlIdentifier("v1"),
                statement_params=mock.ANY,
            )
            self.assertEqual(
                mv,
                model_version_impl.ModelVersion._ref(
                    self.m_r._model_ops,
                    model_name=sql_identifier.SqlIdentifier("MODEL"),
                    version_name=sql_identifier.SqlIdentifier("v1"),
                ),
            )

    def test_log_model_2(self) -> None:
        m_model = mock.MagicMock()
        m_pip_requirements = mock.MagicMock()
        m_signatures = mock.MagicMock()
        m_options = mock.MagicMock()
        m_stage_path = "@TEMP.TEST.MODEL/V1"
        with mock.patch.object(self.m_r._model_ops, "validate_existence", return_value=False), mock.patch.object(
            self.m_r._model_ops, "prepare_model_stage_path", return_value=m_stage_path
        ) as mock_prepare_model_stage_path, mock.patch.object(
            model_composer.ModelComposer, "save"
        ) as mock_save, mock.patch.object(
            self.m_r._model_ops, "create_from_stage"
        ) as mock_create_from_stage:
            mv = self.m_r.log_model(
                model=m_model,
                model_name="MODEL",
                version_name="V1",
                pip_requirements=m_pip_requirements,
                signatures=m_signatures,
                options=m_options,
            )
            mock_prepare_model_stage_path.assert_called_once_with(
                statement_params=mock.ANY,
            )
            mock_save.assert_called_once_with(
                name="MODEL",
                model=m_model,
                signatures=m_signatures,
                sample_input_data=None,
                conda_dependencies=None,
                pip_requirements=m_pip_requirements,
                python_version=None,
                code_paths=None,
                ext_modules=None,
                options=m_options,
            )
            mock_create_from_stage.assert_called_once_with(
                composed_model=mock.ANY,
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                version_name=sql_identifier.SqlIdentifier("V1"),
                statement_params=mock.ANY,
            )
            self.assertEqual(
                mv,
                model_version_impl.ModelVersion._ref(
                    self.m_r._model_ops,
                    model_name=sql_identifier.SqlIdentifier("MODEL"),
                    version_name=sql_identifier.SqlIdentifier("V1"),
                ),
            )

    def test_log_model_3(self) -> None:
        m_model = mock.MagicMock()
        m_python_version = mock.MagicMock()
        m_code_paths = mock.MagicMock()
        m_ext_modules = mock.MagicMock()
        m_stage_path = "@TEMP.TEST.MODEL/V1"
        with mock.patch.object(self.m_r._model_ops, "validate_existence", return_value=False), mock.patch.object(
            self.m_r._model_ops, "prepare_model_stage_path", return_value=m_stage_path
        ) as mock_prepare_model_stage_path, mock.patch.object(
            model_composer.ModelComposer, "save"
        ) as mock_save, mock.patch.object(
            self.m_r._model_ops, "create_from_stage"
        ) as mock_create_from_stage:
            mv = self.m_r.log_model(
                model=m_model,
                model_name="MODEL",
                version_name="V1",
                python_version=m_python_version,
                code_paths=m_code_paths,
                ext_modules=m_ext_modules,
            )
            mock_prepare_model_stage_path.assert_called_once_with(
                statement_params=mock.ANY,
            )
            mock_save.assert_called_once_with(
                name="MODEL",
                model=m_model,
                signatures=None,
                sample_input_data=None,
                conda_dependencies=None,
                pip_requirements=None,
                python_version=m_python_version,
                code_paths=m_code_paths,
                ext_modules=m_ext_modules,
                options=None,
            )
            mock_create_from_stage.assert_called_once_with(
                composed_model=mock.ANY,
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                version_name=sql_identifier.SqlIdentifier("V1"),
                statement_params=mock.ANY,
            )
            self.assertEqual(
                mv,
                model_version_impl.ModelVersion._ref(
                    self.m_r._model_ops,
                    model_name=sql_identifier.SqlIdentifier("MODEL"),
                    version_name=sql_identifier.SqlIdentifier("V1"),
                ),
            )

    def test_log_model_4(self) -> None:
        m_model = mock.MagicMock()
        m_stage_path = "@TEMP.TEST.MODEL/V1"
        with mock.patch.object(self.m_r._model_ops, "validate_existence", return_value=False), mock.patch.object(
            self.m_r._model_ops, "prepare_model_stage_path", return_value=m_stage_path
        ) as mock_prepare_model_stage_path, mock.patch.object(
            model_composer.ModelComposer, "save"
        ) as mock_save, mock.patch.object(
            self.m_r._model_ops, "create_from_stage"
        ) as mock_create_from_stage, mock.patch.object(
            self.m_r._model_ops, "set_comment"
        ) as mock_set_comment, mock.patch.object(
            self.m_r._model_ops._metadata_ops, "save"
        ) as mock_metadata_save:
            mv = self.m_r.log_model(
                model=m_model, model_name="MODEL", version_name="V1", comment="this is comment", metrics={"a": 1}
            )
            mock_prepare_model_stage_path.assert_called_once_with(
                statement_params=mock.ANY,
            )
            mock_save.assert_called_once_with(
                name="MODEL",
                model=m_model,
                signatures=None,
                sample_input_data=None,
                conda_dependencies=None,
                pip_requirements=None,
                python_version=None,
                code_paths=None,
                ext_modules=None,
                options=None,
            )
            mock_create_from_stage.assert_called_once_with(
                composed_model=mock.ANY,
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                version_name=sql_identifier.SqlIdentifier("V1"),
                statement_params=mock.ANY,
            )
            self.assertEqual(
                mv,
                model_version_impl.ModelVersion._ref(
                    self.m_r._model_ops,
                    model_name=sql_identifier.SqlIdentifier("MODEL"),
                    version_name=sql_identifier.SqlIdentifier("V1"),
                ),
            )
            mock_set_comment.assert_called_once_with(
                comment="this is comment",
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                version_name=sql_identifier.SqlIdentifier("V1"),
                statement_params=mock.ANY,
            )
            mock_metadata_save.assert_called_once_with(
                {"metrics": {"a": 1}},
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                version_name=sql_identifier.SqlIdentifier("V1"),
                statement_params=mock.ANY,
            )

    def test_log_model_5(self) -> None:
        m_model = mock.MagicMock()
        with mock.patch.object(self.m_r._model_ops, "validate_existence", return_value=True) as mock_validate_existence:
            with self.assertRaisesRegex(ValueError, "Model MODEL version V1 already existed."):
                self.m_r.log_model(model=m_model, model_name="MODEL", version_name="V1")
            mock_validate_existence.assert_has_calls(
                [
                    mock.call(
                        model_name=sql_identifier.SqlIdentifier("MODEL"),
                        statement_params=mock.ANY,
                    ),
                    mock.call(
                        model_name=sql_identifier.SqlIdentifier("MODEL"),
                        version_name=sql_identifier.SqlIdentifier("V1"),
                        statement_params=mock.ANY,
                    ),
                ]
            )

    def test_delete_model(self) -> None:
        with mock.patch.object(self.m_r._model_ops, "delete_model_or_version") as mock_delete_model_or_version:
            self.m_r.delete_model(
                model_name="MODEL",
            )
            mock_delete_model_or_version.assert_called_once_with(
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                statement_params=mock.ANY,
            )


if __name__ == "__main__":
    absltest.main()
