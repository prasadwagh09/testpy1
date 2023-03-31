#!/usr/bin/env python3
#
# Copyright (c) 2012-2022 Snowflake Computing Inc. All rights reserved.
#
import numpy as np
import pandas as pd
import pytest
from absl.testing.absltest import TestCase, main

from snowflake.ml.framework.base import BaseTransformer
from snowflake.ml.preprocessing import MinMaxScaler, StandardScaler
from snowflake.ml.utils.connection_params import SnowflakeLoginOptions
from snowflake.snowpark import Session
from snowflake.snowpark.exceptions import SnowparkColumnException
from tests.integ.snowflake.ml.framework import utils as framework_utils
from tests.integ.snowflake.ml.framework.utils import (
    DATA,
    DATA_NONE_NAN,
    NUMERIC_COLS,
    OUTPUT_COLS,
    SCHEMA,
)


class TestBaseFunctions(TestCase):
    """Test Base."""

    def setUp(self):
        """Creates Snowpark and Snowflake environments for testing."""
        self._session = Session.builder.configs(SnowflakeLoginOptions()).create()

    def tearDown(self):
        self._session.close()

    def test_fit_input_cols_check(self):
        """
        Verify the input columns check during fitting.

        Raises
        ------
        AssertionError
            If no error on input columns is raised during fitting.
        """
        _, df = framework_utils.get_df(self._session, DATA, SCHEMA)

        scaler = MinMaxScaler()
        with pytest.raises(RuntimeError) as excinfo:
            scaler.fit(df)
        assert "input_cols is not set." in excinfo.value.args[0]

    def test_transform_input_cols_check(self):
        """
        Verify the input columns check during transform.

        Raises
        ------
        AssertionError
            If no error on input columns is raised during transform.
        """
        input_cols, output_cols = NUMERIC_COLS, OUTPUT_COLS
        _, df = framework_utils.get_df(self._session, DATA, SCHEMA)

        scaler = MinMaxScaler().set_input_cols(input_cols).set_output_cols(output_cols)
        scaler.fit(df)
        scaler.set_input_cols([])
        with pytest.raises(RuntimeError) as excinfo:
            scaler.transform(df)
        assert "input_cols is not set." in excinfo.value.args[0]

    def test_transform_output_cols_check(self):
        """
        Verify the output columns check during transform.

        Raises
        ------
        AssertionError
            If no error on output columns is raised during transform.
        """
        input_cols, output_cols = NUMERIC_COLS, OUTPUT_COLS
        _, df = framework_utils.get_df(self._session, DATA, SCHEMA)

        # output_cols not set
        scaler = MinMaxScaler().set_input_cols(input_cols)
        scaler.fit(df)
        with pytest.raises(RuntimeError) as excinfo:
            scaler.transform(df)
        assert "output_cols is not set." in excinfo.value.args[0]

        # output_cols of mismatched sizes
        undersized_output_cols = output_cols[:-1]
        scaler = MinMaxScaler().set_input_cols(input_cols).set_output_cols(undersized_output_cols)
        scaler.fit(df)
        with pytest.raises(RuntimeError) as excinfo:
            scaler.transform(df)
        assert "Size mismatch" in excinfo.value.args[0]

        oversized_output_cols = output_cols.copy()
        oversized_output_cols.append("OUT_OVER")
        scaler = MinMaxScaler().set_input_cols(input_cols).set_output_cols(oversized_output_cols)
        scaler.fit(df)
        with pytest.raises(RuntimeError) as excinfo:
            scaler.transform(df)
        assert "Size mismatch" in excinfo.value.args[0]

    def test_get_sklearn_object(self):
        input_cols = ["F"]
        output_cols = ["F"]
        pandas_df_1 = pd.DataFrame(data={"F": [1, 2, 3]})
        pandas_df_2 = pd.DataFrame(data={"F": [4, 5, 6]})

        snow_df_1 = self._session.create_dataframe(pandas_df_1)
        snow_df_2 = self._session.create_dataframe(pandas_df_2)

        scaler = StandardScaler(input_cols=input_cols, output_cols=output_cols)
        scaler.fit(snow_df_1)
        sk_object_1 = scaler.get_sklearn_object()
        assert np.allclose([sk_object_1.mean_], [2.0])
        scaler.fit(snow_df_2)
        sk_object_2 = scaler.get_sklearn_object()
        assert np.allclose([sk_object_2.mean_], [5.0])

    def test_validate_data_has_no_nulls(self):
        input_cols = NUMERIC_COLS
        _, df = framework_utils.get_df(self._session, DATA, SCHEMA, np.nan)
        _, df_with_nulls = framework_utils.get_df(self._session, DATA_NONE_NAN, SCHEMA, np.nan)

        class TestTransformer(BaseTransformer):
            pass

        # Assert that numeric data with no null data passes
        transformer = TestTransformer().set_input_cols(input_cols)
        transformer._validate_data_has_no_nulls(df)

        # Assert that numeric data with null data raises
        transformer = TestTransformer().set_input_cols(input_cols)
        with pytest.raises(ValueError) as excinfo:
            transformer._validate_data_has_no_nulls(df_with_nulls)
        assert "Dataset may not contain nulls" in excinfo.value.args[0]

        # Assert that extra input columns raises
        transformer = TestTransformer().set_input_cols(input_cols + ["nonexistent_column"])
        with pytest.raises(SnowparkColumnException) as excinfo:
            transformer._validate_data_has_no_nulls(df)
        assert "The DataFrame does not contain the column" in excinfo.value.args[0]


if __name__ == "__main__":
    main()
