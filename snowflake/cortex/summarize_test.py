import _test_util
from absl.testing import absltest

from snowflake import snowpark
from snowflake.cortex import _summarize
from snowflake.snowpark import functions, types


class SummarizeTest(absltest.TestCase):
    prompt = "|prompt|"

    @staticmethod
    def summarize_for_test(prompt: str) -> str:
        return f"summarized: {prompt}"

    def setUp(self) -> None:
        self._session = _test_util.create_test_session()
        functions.udf(
            self.summarize_for_test,
            name="summarize",
            return_type=types.StringType(),
            input_types=[types.StringType()],
            is_permanent=False,
        )

    def tearDown(self) -> None:
        self._session.sql("drop function summarize(string)").collect()
        self._session.close()

    def test_summarize_str(self) -> None:
        res = _summarize._summarize_impl("summarize", self.prompt)
        self.assertEqual(self.summarize_for_test(self.prompt), res)

    def test_summarize_column(self) -> None:
        df_in = self._session.create_dataframe([snowpark.Row(prompt=self.prompt)])
        df_out = df_in.select(_summarize._summarize_impl("summarize", functions.col("prompt")))
        res = df_out.collect()[0][0]
        self.assertEqual(self.summarize_for_test(self.prompt), res)


if __name__ == "__main__":
    absltest.main()
