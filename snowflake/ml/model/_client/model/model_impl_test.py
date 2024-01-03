from typing import cast
from unittest import mock

from absl.testing import absltest

from snowflake.ml._internal.utils import sql_identifier
from snowflake.ml.model._client.model import model_impl, model_version_impl
from snowflake.ml.model._client.ops import model_ops
from snowflake.ml.test_utils import mock_session
from snowflake.snowpark import Session


class ModelImplTest(absltest.TestCase):
    def setUp(self) -> None:
        self.m_session = mock_session.MockSession(conn=None, test_case=self)
        self.c_session = cast(Session, self.m_session)
        self.m_model = model_impl.Model._ref(
            model_ops.ModelOperator(
                self.c_session,
                database_name=sql_identifier.SqlIdentifier("TEMP"),
                schema_name=sql_identifier.SqlIdentifier("test", case_sensitive=True),
            ),
            model_name=sql_identifier.SqlIdentifier("MODEL"),
        )

    def test_property(self) -> None:
        self.assertEqual(self.m_model.name, "MODEL")
        self.assertEqual(self.m_model.fully_qualified_name, 'TEMP."test".MODEL')

    def test_version_1(self) -> None:
        m_mv = model_version_impl.ModelVersion._ref(
            self.m_model._model_ops,
            model_name=sql_identifier.SqlIdentifier("MODEL"),
            version_name=sql_identifier.SqlIdentifier("V1"),
        )
        with mock.patch.object(
            self.m_model._model_ops, "validate_existence", return_value=True
        ) as mock_validate_existence:
            mv = self.m_model.version("v1")
            self.assertEqual(mv, m_mv)
            mock_validate_existence.assert_called_once_with(
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                version_name=sql_identifier.SqlIdentifier("V1"),
                statement_params=mock.ANY,
            )

    def test_version_2(self) -> None:
        with mock.patch.object(
            self.m_model._model_ops, "validate_existence", return_value=False
        ) as mock_validate_existence:
            with self.assertRaisesRegex(ValueError, 'Unable to find version with name V1 in model TEMP."test"'):
                self.m_model.version("v1")
            mock_validate_existence.assert_called_once_with(
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                version_name=sql_identifier.SqlIdentifier("V1"),
                statement_params=mock.ANY,
            )

    def test_show_versions(self) -> None:
        m_mv_1 = model_version_impl.ModelVersion._ref(
            self.m_model._model_ops,
            model_name=sql_identifier.SqlIdentifier("MODEL"),
            version_name=sql_identifier.SqlIdentifier("V1"),
        )
        m_mv_2 = model_version_impl.ModelVersion._ref(
            self.m_model._model_ops,
            model_name=sql_identifier.SqlIdentifier("MODEL"),
            version_name=sql_identifier.SqlIdentifier("v1", case_sensitive=True),
        )
        with mock.patch.object(
            self.m_model._model_ops,
            "list_models_or_versions",
            return_value=[sql_identifier.SqlIdentifier("V1"), sql_identifier.SqlIdentifier("v1", case_sensitive=True)],
        ) as mock_list_models_or_versions:
            mv_list = self.m_model.show_versions()
            self.assertListEqual(mv_list, [m_mv_1, m_mv_2])
            mock_list_models_or_versions.assert_called_once_with(
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                statement_params=mock.ANY,
            )

    def test_description_getter(self) -> None:
        with mock.patch.object(
            self.m_model._model_ops, "get_comment", return_value="this is a comment"
        ) as mock_get_comment:
            self.assertEqual("this is a comment", self.m_model.description)
            mock_get_comment.assert_called_once_with(
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                statement_params=mock.ANY,
            )

    def test_description_setter(self) -> None:
        with mock.patch.object(self.m_model._model_ops, "set_comment") as mock_set_comment:
            self.m_model.description = "this is a comment"
            mock_set_comment.assert_called_once_with(
                comment="this is a comment",
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                statement_params=mock.ANY,
            )

    def test_comment_getter(self) -> None:
        with mock.patch.object(
            self.m_model._model_ops, "get_comment", return_value="this is a comment"
        ) as mock_get_comment:
            self.assertEqual("this is a comment", self.m_model.comment)
            mock_get_comment.assert_called_once_with(
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                statement_params=mock.ANY,
            )

    def test_comment_setter(self) -> None:
        with mock.patch.object(self.m_model._model_ops, "set_comment") as mock_set_comment:
            self.m_model.comment = "this is a comment"
            mock_set_comment.assert_called_once_with(
                comment="this is a comment",
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                statement_params=mock.ANY,
            )

    def test_default_getter(self) -> None:
        with mock.patch.object(
            self.m_model._model_ops,
            "get_default_version",
            return_value=sql_identifier.SqlIdentifier("V1", case_sensitive=True),
        ) as mock_get_default_version, mock.patch.object(
            self.m_model._model_ops, "validate_existence", return_value=True
        ):
            self.assertEqual("V1", self.m_model.default.version_name)
            mock_get_default_version.assert_called_once_with(
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                statement_params=mock.ANY,
            )

    def test_default_setter(self) -> None:
        with mock.patch.object(self.m_model._model_ops, "set_default_version") as mock_set_default_version:
            self.m_model.default = "V1"  # type: ignore[assignment]
            mock_set_default_version.assert_called_once_with(
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                version_name=sql_identifier.SqlIdentifier("V1"),
                statement_params=mock.ANY,
            )

        with mock.patch.object(self.m_model._model_ops, "set_default_version") as mock_set_default_version:
            mv = model_version_impl.ModelVersion._ref(
                self.m_model._model_ops,
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                version_name=sql_identifier.SqlIdentifier("V2"),
            )
            self.m_model.default = mv
            mock_set_default_version.assert_called_once_with(
                model_name=sql_identifier.SqlIdentifier("MODEL"),
                version_name=sql_identifier.SqlIdentifier("V2"),
                statement_params=mock.ANY,
            )


if __name__ == "__main__":
    absltest.main()
