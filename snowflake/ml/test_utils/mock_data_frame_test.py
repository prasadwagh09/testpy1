from absl.testing.absltest import TestCase, main

from snowflake.ml.test_utils import mock_data_frame
from snowflake.snowpark import DataFrame, Row
from snowflake.snowpark._internal.analyzer.expression import Literal
from snowflake.snowpark.functions import col


class MockDataFrameTest(TestCase):
    """Testing MockDataFrame function."""

    def test_isinstance(self) -> None:
        self.assertTrue(mock_data_frame.MockDataFrame(), DataFrame)

    def test_constructor_collect(self) -> None:
        """Tests the basic operation of MockDataFrame creation and calling collect()."""
        result = [Row(test_column="test_value")]
        mock_df = mock_data_frame.MockDataFrame(result)
        self.assertEqual(mock_df.collect(), result)

    def test_constructor_count(self) -> None:
        """Test the basic operation of MockDataFrame operation and calling count()."""
        mock_df = mock_data_frame.MockDataFrame(count_result=23)
        self.assertEqual(mock_df.count(), 23)

    def test_constructor_collect_and_count_fail(self) -> None:
        """Test that the constructor fails if we specify both results for collect() and count()."""
        with self.assertRaises(AssertionError):
            mock_data_frame.MockDataFrame(collect_result=[], count_result=0)

    def test_wrong_operation_collect(self) -> None:
        """Test that the dataframe operation fails if collect() is called but count() is expected."""
        mock_df = mock_data_frame.MockDataFrame(count_result=42)
        with self.assertRaises(AssertionError):
            mock_df.collect()

    def test_wrong_operation_count(self) -> None:
        """Test that the dataframe operation fails if count() is called but collect() is expected."""
        mock_df = mock_data_frame.MockDataFrame(collect_result=[])
        with self.assertRaises(AssertionError):
            mock_df.count()

    def test_filter_operation(self) -> None:
        """Test that the dataframe filter operation is validated."""
        mock_df = mock_data_frame.MockDataFrame()
        mock_df.add_operation(
            operation="filter",
            args=(col("NAME") == Literal("name"),),
        )
        mock_df.add_count_result(5)
        self.assertEqual(mock_df.filter(col("NAME") == Literal("name")).count(), 5)

    def test_missing_filter_operation(self) -> None:
        """Test that if don't execute an operation in the sequence, an assertion fails."""
        mock_df = mock_data_frame.MockDataFrame(check_call_sequence_completion=False)
        mock_df.add_operation(operation="filter")
        mock_df.add_count_result(5)
        with self.assertRaises(AssertionError):
            mock_df.count()

    def test_drop_operation(self) -> None:
        """Test that the dataframe drop operation is validated."""
        mock_df = mock_data_frame.MockDataFrame()
        mock_df.add_mock_drop("NAME")
        mock_df.add_count_result(5)
        self.assertEqual(mock_df.drop("NAME").count(), 5)

    def test_wrong_drop_operation(self) -> None:
        """Test that the dataframe drop operation is validated."""
        mock_df = mock_data_frame.MockDataFrame()
        mock_df.add_mock_drop("NAME")
        mock_df.add_count_result(5)
        with self.assertRaises(AssertionError):
            mock_df.drop("VALUE").count()

    def test_missing_drop_operation(self) -> None:
        """Test that if don't execute an operation in the sequence, an assertion fails."""
        mock_df = mock_data_frame.MockDataFrame(check_call_sequence_completion=False)
        mock_df.add_mock_drop("NAME")
        mock_df.add_count_result(5)
        with self.assertRaises(AssertionError):
            mock_df.count()

    def test_sort_operation(self) -> None:
        mock_df = mock_data_frame.MockDataFrame()
        mock_df.add_mock_sort("NAME")
        mock_df.add_count_result(5)
        self.assertEqual(mock_df.sort("NAME").count(), 5)

    def test_sort_operation_with_kwargs(self) -> None:
        mock_df = mock_data_frame.MockDataFrame()
        mock_df.add_mock_sort("NAME", ascending=True)
        mock_df.add_count_result(5)
        self.assertEqual(mock_df.sort("NAME", ascending=True).count(), 5)

    def test_wrong_sort_operation(self) -> None:
        mock_df = mock_data_frame.MockDataFrame()
        mock_df.add_mock_sort("NAME")
        mock_df.add_count_result(5)
        with self.assertRaises(AssertionError):
            mock_df.sort("VALUE").count()

    def test_wrong_operation_with_kwargs(self) -> None:
        mock_df = mock_data_frame.MockDataFrame()
        mock_df.add_mock_sort("NAME", ascending=True)
        mock_df.add_count_result(5)
        with self.assertRaises(AssertionError):
            mock_df.sort("NAME").count()

    def test_missing_sort_operation(self) -> None:
        mock_df = mock_data_frame.MockDataFrame(check_call_sequence_completion=False)
        mock_df.add_mock_sort("NAME")
        mock_df.add_count_result(5)
        with self.assertRaises(AssertionError):
            mock_df.count()

    def test_with_columns_operation(self) -> None:
        mock_df = mock_data_frame.MockDataFrame()
        mock_df.add_mock_with_columns(col_names=["NAME"], values=[col("NAME")])
        mock_df.add_count_result(5)
        self.assertEqual(mock_df.with_columns(col_names=["NAME"], values=[col("NAME")]).count(), 5)

    def test_missing_with_columns_operation(self) -> None:
        mock_df = mock_data_frame.MockDataFrame(check_call_sequence_completion=False)
        mock_df.add_mock_with_columns(col_names=["NAME"], values=[col("NAME")])
        mock_df.add_count_result(5)
        with self.assertRaises(AssertionError):
            mock_df.count()

    def test_missing_operation(self) -> None:
        """Test that an assertion fails if we destroy a MockDataFrame without completing all expected operations."""
        with self.assertRaises(AssertionError):
            with mock_data_frame.MockDataFrame(count_result=10):
                pass

    def test_select_operation(self) -> None:
        """Test that the dataframe select operation is validated."""
        mock_df = mock_data_frame.MockDataFrame()
        mock_df.add_operation(
            operation="select",
            args=("NAME",),
        )
        mock_df.add_count_result(5)
        self.assertEqual(mock_df.select("NAME").count(), 5)

    def test_statement_params_success(self) -> None:
        """Test that the dataframe select operation is validated."""
        mock_df = mock_data_frame.MockDataFrame()
        mock_df.add_operation(
            operation="select",
            args=("NAME",),
            kwargs={"statement_params": {"project": "SnowML"}},
            check_statement_params=True,
        )
        mock_df.add_count_result(5)
        self.assertEqual(mock_df.select("NAME", statement_params={"project": "SnowML"}).count(), 5)

    def test_statement_params_mismatch(self) -> None:
        """Test that the dataframe select operation is validated."""
        mock_df = mock_data_frame.MockDataFrame()
        mock_df.add_operation(
            operation="select",
            args=("NAME",),
            kwargs={"statement_params": {"project": "SnowML"}},
            check_statement_params=True,
        )
        mock_df.add_count_result(5)
        with self.assertRaises(AssertionError):
            self.assertEqual(mock_df.select("NAME", statement_params={"project": "SnowPark"}).count(), 5)

    def test_statement_params_missing(self) -> None:
        """Test that the dataframe select operation is validated."""
        mock_df = mock_data_frame.MockDataFrame()
        mock_df.add_operation(
            operation="select",
            args=("NAME",),
            kwargs={"statement_params": {"project": "SnowML"}},
            check_statement_params=True,
        )
        mock_df.add_count_result(5)
        with self.assertRaises(AssertionError):
            self.assertEqual(mock_df.select("NAME").count(), 5)

    def test_queries(self) -> None:
        """Test that adding and accessing queries in the dataframe works."""
        mock_df = mock_data_frame.MockDataFrame()
        test_data = [
            {"type": "queries", "index": 0, "value": "SELECT query_1 FROM TABLE;"},
            {"type": "queries", "index": 1, "value": "SELECT query_2 FROM TABLE;"},
            {"type": "post_actions", "index": 0, "value": "post_action_1"},
            {"type": "post_actions", "index": 1, "value": "post_action_2"},
        ]
        for t in test_data:
            mock_df.add_query(str(t["type"]), str(t["value"]))

        self.assertEqual(
            mock_df.queries,
            {
                "queries": [test_data[0]["value"], test_data[1]["value"]],
                "post_actions": [test_data[2]["value"], test_data[3]["value"]],
            },
        )


if __name__ == "__main__":
    main()
