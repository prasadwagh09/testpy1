from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from snowflake.ml._internal.utils.identifier import (
    get_inferred_name,
    get_unescaped_names,
)
from snowflake.ml.feature_store.entity import Entity
from snowflake.snowpark import DataFrame, Session
from snowflake.snowpark.types import (
    DateType,
    StructType,
    TimestampType,
    TimeType,
    _NumericType,
)

FEATURE_VIEW_NAME_DELIMITER = "$"
TIMESTAMP_COL_PLACEHOLDER = "FS_TIMESTAMP_COL_PLACEHOLDER_VAL"
FEATURE_OBJ_TYPE = "FEATURE_OBJ_TYPE"


class FeatureViewStatus(Enum):
    DRAFT = "DRAFT"
    STATIC = "STATIC"
    RUNNING = "RUNNING"
    SUSPENDED = "SUSPENDED"


@dataclass(frozen=True)
class FeatureViewSlice:
    feature_view_ref: FeatureView
    names: List[str]

    def __repr__(self) -> str:
        states = (f"{k}={v}" for k, v in vars(self).items())
        return f"{type(self).__name__}({', '.join(states)})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FeatureViewSlice):
            return False

        return (
            get_unescaped_names(self.names) == get_unescaped_names(other.names)
            and self.feature_view_ref == other.feature_view_ref
        )

    def to_json(self) -> str:
        fvs_dict = {
            "feature_view_ref": self.feature_view_ref.to_json(),
            "names": self.names,
            FEATURE_OBJ_TYPE: self.__class__.__name__,
        }
        return json.dumps(fvs_dict)

    @classmethod
    def from_json(cls, json_str: str, session: Session) -> FeatureViewSlice:
        json_dict = json.loads(json_str)
        if FEATURE_OBJ_TYPE not in json_dict or json_dict[FEATURE_OBJ_TYPE] != cls.__name__:
            raise ValueError(f"Invalid json str for {cls.__name__}: {json_str}")
        del json_dict[FEATURE_OBJ_TYPE]
        json_dict["feature_view_ref"] = FeatureView.from_json(json_dict["feature_view_ref"], session)
        return cls(**json_dict)


class FeatureView:
    """
    A FeatureView instance encapsulates a logical group of features.
    """

    def __init__(
        self,
        name: str,
        entities: List[Entity],
        feature_df: DataFrame,
        timestamp_col: Optional[str] = None,
        desc: str = "",
    ) -> None:
        """
        Create a FeatureView instance.

        Args:
            name: name of the FeatureView. NOTE: FeatureView name will be capitalized.
            entities: entities that the FeatureView is associated with.
            feature_df: Snowpark DataFrame containing data source and all feature feature_df logics.
                Final projection of the DataFrame should contain feature names, join keys and timestamp(if applicable).
            timestamp_col: name of the timestamp column for point-in-time lookup when consuming the feature values.
            desc: description of the FeatureView.
        """
        self._name: str = name
        self._entities: List[Entity] = entities
        self._feature_df: DataFrame = feature_df
        self._timestamp_col: Optional[str] = timestamp_col if timestamp_col is not None else None
        self._desc: str = desc
        self._query: str = self._get_query()
        self._version: Optional[str] = None
        self._status: FeatureViewStatus = FeatureViewStatus.DRAFT
        self._feature_desc: OrderedDict[str, Optional[str]] = OrderedDict((f, None) for f in self._get_feature_names())
        self._refresh_freq: Optional[str] = None
        self._database: Optional[str] = None
        self._schema: Optional[str] = None
        self._warehouse: Optional[str] = None
        self._validate()

    def slice(self, names: List[str]) -> FeatureViewSlice:
        """
        Select a subset of features within the FeatureView.

        Args:
            names: feature names to select.

        Returns:
            FeatureViewSlice instance containing selected features.

        Raises:
            ValueError: if selected feature names is not found in the FeatureView.
        """
        res = []
        for name in names:
            name = get_unescaped_names(name)
            if name not in self.feature_names:
                raise ValueError(f"Feature name {name} not found in FeatureView {self.name}.")
            res.append(name)
        return FeatureViewSlice(self, res)

    def fully_qualified_name(self) -> str:
        """
        Returns the fully qualified name for the FeatureView in Snowflake storage.

        Returns:
            fully qualified name string

        Raises:
            RuntimeError: if the FeatureView is not materialized.
        """
        if self.status == FeatureViewStatus.DRAFT:
            raise RuntimeError(f"FeatureView {self.name} has not been materialized.")
        return f"{self._database}.{self._schema}.{self.name}{FEATURE_VIEW_NAME_DELIMITER}{self.version}"

    def attach_feature_desc(self, descs: Dict[str, str]) -> FeatureView:
        """
        Associate feature level descriptions to the FeatureView.

        Args:
            descs: Dictionary contains feature name and corresponding descriptions.

        Returns:
            FeatureView with feature level desc attached.

        Raises:
            ValueError: if feature name is not found in the FeatureView.
        """
        for f, d in descs.items():
            f = get_unescaped_names(f)
            if f not in self._feature_desc:
                raise ValueError(
                    f"Feature name {f} is not found in FeatureView {self.name}, "
                    f"valid feature names are: {self.feature_names}"
                )
            self._feature_desc[f] = d
        return self

    @property
    def name(self) -> str:
        return self._name

    @property
    def entities(self) -> List[Entity]:
        return self._entities

    @property
    def feature_df(self) -> DataFrame:
        return self._feature_df

    @property
    def timestamp_col(self) -> Optional[str]:
        return self._timestamp_col

    @property
    def desc(self) -> str:
        return self._desc

    @property
    def query(self) -> str:
        return self._query

    @property
    def version(self) -> Optional[str]:
        return self._version

    @property
    def status(self) -> FeatureViewStatus:
        return self._status

    @property
    def feature_names(self) -> List[str]:
        return list(self._feature_desc.keys())

    @property
    def feature_descs(self) -> Dict[str, Optional[str]]:
        return dict(self._feature_desc)

    @property
    def refresh_freq(self) -> Optional[str]:
        return self._refresh_freq

    @property
    def database(self) -> Optional[str]:
        return self._database

    @property
    def schema(self) -> Optional[str]:
        return self._schema

    @property
    def warehouse(self) -> Optional[str]:
        return self._warehouse

    @property
    def output_schema(self) -> StructType:
        return self._feature_df.schema

    def _get_query(self) -> str:
        if len(self._feature_df.queries["queries"]) != 1:
            raise ValueError(
                f"""feature_df dataframe must contain only 1 query.
Got {len(self._feature_df.queries['queries'])}: {self._feature_df.queries['queries']}
"""
            )
        return str(self._feature_df.queries["queries"][0])

    def _validate(self) -> None:
        if FEATURE_VIEW_NAME_DELIMITER in self._name:
            raise ValueError(
                f"FeatureView name `{self._name}` contains invalid character `{FEATURE_VIEW_NAME_DELIMITER}`."
            )

        unescaped_df_cols = get_unescaped_names(self._feature_df.columns)
        for e in self._entities:
            for k in get_unescaped_names(e.join_keys):
                if k not in unescaped_df_cols:
                    raise ValueError(
                        f"join_key {k} in Entity {e.name} is not found in input dataframe: {unescaped_df_cols}"
                    )

        if self._timestamp_col is not None:
            ts_col = get_unescaped_names(self._timestamp_col)
            if ts_col == TIMESTAMP_COL_PLACEHOLDER:
                raise ValueError(f"Invalid timestamp_col name, cannot be {TIMESTAMP_COL_PLACEHOLDER}.")
            if ts_col not in get_unescaped_names(self._feature_df.columns):
                raise ValueError(f"timestamp_col {ts_col} is not found in input dataframe.")

            col_type = self._feature_df.schema[get_inferred_name(ts_col)].datatype
            if not isinstance(col_type, (DateType, TimeType, TimestampType, _NumericType)):
                raise ValueError(f"Invalid data type for timestamp_col {ts_col}: {col_type}.")

    def _get_feature_names(self) -> List[str]:
        join_keys = [k for e in self._entities for k in get_unescaped_names(e.join_keys)]
        ts_col = [get_unescaped_names(self._timestamp_col)] if self._timestamp_col is not None else []
        return [c for c in get_unescaped_names(self._feature_df.columns) if c not in join_keys + ts_col]

    def __repr__(self) -> str:
        states = (f"{k}={v}" for k, v in vars(self).items())
        return f"{type(self).__name__}({', '.join(states)})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FeatureView):
            return False

        return (
            get_unescaped_names(self.name) == get_unescaped_names(other.name)
            and get_unescaped_names(self.version) == get_unescaped_names(other.version)
            and get_unescaped_names(self.timestamp_col) == get_unescaped_names(other.timestamp_col)
            and self.entities == other.entities
            and self.desc == other.desc
            and self.feature_descs == other.feature_descs
            and self.feature_names == other.feature_names
            and self.query == other.query
            and self.refresh_freq == other.refresh_freq
            and str(self.status) == str(other.status)
            and self.warehouse == other.warehouse
        )

    def _to_dict(self) -> Dict[str, str]:
        fv_dict = self.__dict__.copy()
        if "_feature_df" in fv_dict:
            fv_dict.pop("_feature_df")
        fv_dict["_entities"] = [e.__dict__ for e in self._entities]
        fv_dict["_status"] = str(self._status)
        return fv_dict

    def to_json(self) -> str:
        state_dict = self._to_dict()
        state_dict[FEATURE_OBJ_TYPE] = self.__class__.__name__
        return json.dumps(state_dict)

    @classmethod
    def from_json(cls, json_str: str, session: Session) -> FeatureView:
        json_dict = json.loads(json_str)
        if FEATURE_OBJ_TYPE not in json_dict or json_dict[FEATURE_OBJ_TYPE] != cls.__name__:
            raise ValueError(f"Invalid json str for {cls.__name__}: {json_str}")

        return FeatureView._construct_feature_view(
            name=json_dict["_name"],
            entities=[Entity(**e) for e in json_dict["_entities"]],
            feature_df=session.sql(json_dict["_query"]),
            timestamp_col=json_dict["_timestamp_col"],
            desc=json_dict["_desc"],
            version=json_dict["_version"],
            status=json_dict["_status"],
            feature_descs=json_dict["_feature_desc"],
            refresh_freq=json_dict["_refresh_freq"],
            database=json_dict["_database"],
            schema=json_dict["_schema"],
            warehouse=json_dict["_warehouse"],
        )

    @staticmethod
    def _construct_feature_view(
        name: str,
        entities: List[Entity],
        feature_df: DataFrame,
        timestamp_col: Optional[str],
        desc: str,
        version: str,
        status: FeatureViewStatus,
        feature_descs: Dict[str, str],
        refresh_freq: Optional[str],
        database: Optional[str],
        schema: Optional[str],
        warehouse: Optional[str],
    ) -> FeatureView:
        fv = FeatureView(
            name=name,
            entities=entities,
            feature_df=feature_df,
            timestamp_col=timestamp_col,
            desc=desc,
        )
        fv._version = version
        fv._status = status
        fv._refresh_freq = refresh_freq
        fv._database = database
        fv._schema = schema
        fv._warehouse = warehouse
        fv.attach_feature_desc(feature_descs)
        return fv
