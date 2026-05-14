"""
connectors.py - unified data source connector service.

Provides a pluggable connector interface for importing data from various sources.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type
import io

import pandas as pd

from utils.logger import logger
from utils.errors import ConnectorValidationError, ConnectorNotFoundError


@dataclass
class ConnectorConfig:
    source_type: str
    name: str
    description: str = ""
    icon: str = "database"
    fields: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ConnectorResult:
    session_id: str
    filename: str
    source: str
    rows: int
    columns: List[str]
    preview: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseConnector(ABC):
    """Abstract base class for all data connectors."""

    config: ConnectorConfig

    @abstractmethod
    def connect(self, params: Dict[str, Any]) -> pd.DataFrame:
        """Connect to source and return a DataFrame."""
        pass

    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate required parameters. Override for custom validation."""
        for field_def in self.config.fields:
            if field_def.get("required") and field_def["name"] not in params:
                raise ConnectorValidationError(
                    f"Missing required field: {field_def['name']}"
                )

    def import_data(
        self, params: Dict[str, Any], owner_id: str, filename: Optional[str] = None
    ) -> ConnectorResult:
        """Full import pipeline: validate → connect → create session."""
        import uuid

        self.validate_params(params)
        df = self.connect(params)

        if filename is None:
            filename = f"{self.config.name}_{params.get('table', params.get('collection', 'import'))}.csv"

        session_id = str(uuid.uuid4())

        logger.info(
            f"Connector '{self.config.name}': {len(df)} rows → session={session_id}"
        )

        from utils.preview import safe_preview

        preview = safe_preview(df)

        return ConnectorResult(
            session_id=session_id,
            filename=filename,
            source=self._build_source_string(params),
            rows=len(df),
            columns=list(df.columns),
            preview=preview,
            metadata={"source_type": self.config.source_type},
        )

    def _build_source_string(self, params: Dict[str, Any]) -> str:
        """Build a human-readable source string."""
        return f"{self.config.name}"


class PostgreSQLConnector(BaseConnector):
    config = ConnectorConfig(
        source_type="postgresql",
        name="PostgreSQL",
        description="Import data from PostgreSQL database",
        icon="postgresql",
        fields=[
            {
                "name": "host",
                "label": "Host",
                "type": "text",
                "required": True,
                "placeholder": "localhost",
            },
            {"name": "port", "label": "Port", "type": "number", "default": "5432"},
            {"name": "database", "label": "Database", "type": "text", "required": True},
            {"name": "schema", "label": "Schema", "type": "text", "default": "public"},
            {"name": "username", "label": "Username", "type": "text", "required": True},
            {
                "name": "password",
                "label": "Password",
                "type": "password",
                "required": True,
            },
            {
                "name": "query",
                "label": "SQL Query",
                "type": "textarea",
                "required": False,
                "placeholder": "SELECT * FROM table_name LIMIT 10000",
            },
            {
                "name": "table",
                "label": "Or Table Name",
                "type": "text",
                "required": False,
            },
            {
                "name": "limit",
                "label": "Row Limit",
                "type": "number",
                "default": "100000",
            },
        ],
    )

    def connect(self, params: Dict[str, Any]) -> pd.DataFrame:
        import sqlalchemy as sa
        from urllib.parse import urlencode

        host = params["host"]
        port = params.get("port", 5432)
        database = params["database"]
        schema = params.get("schema", "public")
        username = params["username"]
        password = params["password"]

        query = params.get("query", "").strip()
        table = params.get("table", "")
        limit = int(params.get("limit", 100000))

        conn_str = f"postgresql://{username}:{password}@{host}:{port}/{database}"
        if schema != "public":
            conn_str += f"?options=-csearch_path%3D{schema}"

        engine = sa.create_engine(conn_str, pool_pre_ping=True)

        if query:
            if not query.upper().startswith("SELECT"):
                raise ConnectorValidationError("Only SELECT queries are allowed")
            sql = query if "LIMIT" in query.upper() else f"{query} LIMIT {limit}"
        elif table:
            sql = f'SELECT * FROM "{schema}"."{table}" LIMIT {limit}'
        else:
            raise ConnectorValidationError("Either 'query' or 'table' must be provided")

        with engine.connect() as conn:
            return pd.read_sql(sa.text(sql), conn)

    def _build_source_string(self, params: Dict[str, Any]) -> str:
        return f"PostgreSQL: {params['host']}/{params['database']}"


class MongoDBConnector(BaseConnector):
    config = ConnectorConfig(
        source_type="mongodb",
        name="MongoDB",
        description="Import data from MongoDB collection",
        icon="mongodb",
        fields=[
            {
                "name": "connection_string",
                "label": "Connection String",
                "type": "text",
                "required": True,
                "placeholder": "mongodb://localhost:27017",
            },
            {"name": "database", "label": "Database", "type": "text", "required": True},
            {
                "name": "collection",
                "label": "Collection",
                "type": "text",
                "required": True,
            },
            {
                "name": "query",
                "label": "Filter (JSON)",
                "type": "textarea",
                "default": "{}",
            },
            {
                "name": "projection",
                "label": "Projection (JSON)",
                "type": "textarea",
                "default": "{}",
            },
            {
                "name": "limit",
                "label": "Document Limit",
                "type": "number",
                "default": "10000",
            },
        ],
    )

    def connect(self, params: Dict[str, Any]) -> pd.DataFrame:
        import json
        from pymongo import MongoClient

        client = MongoClient(params["connection_string"])
        db = client[params["database"]]
        collection = db[params["collection"]]

        query = json.loads(params.get("query", "{}") or "{}")
        projection = json.loads(params.get("projection", "{}") or "{}") or None
        limit = int(params.get("limit", 10000))

        cursor = collection.find(query, projection).limit(limit)
        records = list(cursor)

        client.close()

        if not records:
            return pd.DataFrame()

        df = pd.json_normalize(records)
        if "_id" in df.columns:
            df["_id"] = df["_id"].astype(str)

        return df

    def _build_source_string(self, params: Dict[str, Any]) -> str:
        return f"MongoDB: {params['database']}.{params['collection']}"


class SnowflakeConnector(BaseConnector):
    config = ConnectorConfig(
        source_type="snowflake",
        name="Snowflake",
        description="Import data from Snowflake data warehouse",
        icon="snowflake",
        fields=[
            {
                "name": "account",
                "label": "Account",
                "type": "text",
                "required": True,
                "placeholder": "xy12345.us-east-1",
            },
            {"name": "username", "label": "Username", "type": "text", "required": True},
            {
                "name": "password",
                "label": "Password",
                "type": "password",
                "required": True,
            },
            {
                "name": "warehouse",
                "label": "Warehouse",
                "type": "text",
                "required": True,
            },
            {"name": "database", "label": "Database", "type": "text", "required": True},
            {"name": "schema", "label": "Schema", "type": "text", "default": "PUBLIC"},
            {
                "name": "query",
                "label": "SQL Query",
                "type": "textarea",
                "required": False,
            },
            {
                "name": "table",
                "label": "Or Table Name",
                "type": "text",
                "required": False,
            },
            {
                "name": "limit",
                "label": "Row Limit",
                "type": "number",
                "default": "100000",
            },
        ],
    )

    def connect(self, params: Dict[str, Any]) -> pd.DataFrame:
        import sqlalchemy as sa

        account = params["account"]
        username = params["username"]
        password = params["password"]
        warehouse = params["warehouse"]
        database = params["database"]
        schema = params.get("schema", "PUBLIC")

        conn_str = (
            f"snowflake://{username}:{password}@{account}/{database}/{schema}"
            f"?warehouse={warehouse}"
        )

        query = params.get("query", "").strip()
        table = params.get("table", "")
        limit = int(params.get("limit", 100000))

        engine = sa.create_engine(conn_str)

        if query:
            if not query.upper().startswith("SELECT"):
                raise ConnectorValidationError("Only SELECT queries are allowed")
            sql = query if "LIMIT" in query.upper() else f"{query} LIMIT {limit}"
        elif table:
            sql = f'SELECT * FROM "{database}"."{schema}"."{table}" LIMIT {limit}'
        else:
            raise ConnectorValidationError("Either 'query' or 'table' must be provided")

        with engine.connect() as conn:
            return pd.read_sql(sa.text(sql), conn)

    def _build_source_string(self, params: Dict[str, Any]) -> str:
        return f"Snowflake: {params['account']}/{params['database']}"


class BigQueryConnector(BaseConnector):
    config = ConnectorConfig(
        source_type="bigquery",
        name="Google BigQuery",
        description="Import data from Google BigQuery",
        icon="bigquery",
        fields=[
            {
                "name": "credentials_json",
                "label": "Service Account JSON",
                "type": "textarea",
                "required": True,
            },
            {
                "name": "project_id",
                "label": "Project ID",
                "type": "text",
                "required": True,
            },
            {
                "name": "query",
                "label": "SQL Query",
                "type": "textarea",
                "required": False,
            },
            {
                "name": "table",
                "label": "Or Table (project.dataset.table)",
                "type": "text",
                "required": False,
            },
            {
                "name": "limit",
                "label": "Row Limit",
                "type": "number",
                "default": "100000",
            },
        ],
    )

    def connect(self, params: Dict[str, Any]) -> pd.DataFrame:
        import json
        from google.cloud import bigquery
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_info(
            json.loads(params["credentials_json"]),
            scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
        )

        client = bigquery.Client(credentials=credentials, project=params["project_id"])

        query = params.get("query", "").strip()
        table = params.get("table", "")
        limit = int(params.get("limit", 100000))

        if query:
            if not query.upper().startswith("SELECT"):
                raise ConnectorValidationError("Only SELECT queries are allowed")
            sql = query if "LIMIT" in query.upper() else f"{query} LIMIT {limit}"
            job = client.query(sql).result()
            df = job.to_dataframe()
        elif table:
            df = (
                client.query(f"SELECT * FROM `{table}` LIMIT {limit}")
                .result()
                .to_dataframe()
            )
        else:
            raise ConnectorValidationError("Either 'query' or 'table' must be provided")

        client.close()
        return df

    def _build_source_string(self, params: Dict[str, Any]) -> str:
        return f"BigQuery: {params['project_id']}"


class RESTAPIConnector(BaseConnector):
    config = ConnectorConfig(
        source_type="rest_api",
        name="REST API",
        description="Import data from any REST API",
        icon="api",
        fields=[
            {
                "name": "url",
                "label": "API URL",
                "type": "text",
                "required": True,
                "placeholder": "https://api.example.com/data",
            },
            {
                "name": "method",
                "label": "HTTP Method",
                "type": "select",
                "options": ["GET", "POST"],
                "default": "GET",
            },
            {
                "name": "headers",
                "label": "Headers (JSON)",
                "type": "textarea",
                "default": '{"Content-Type": "application/json"}',
            },
            {"name": "body", "label": "Request Body (JSON)", "type": "textarea"},
            {
                "name": "auth_type",
                "label": "Auth Type",
                "type": "select",
                "options": ["none", "bearer", "basic", "api_key"],
            },
            {"name": "auth_value", "label": "Auth Value", "type": "text"},
            {
                "name": "data_path",
                "label": "Data Path (JSON path)",
                "type": "text",
                "placeholder": "data.results",
                "default": "",
            },
            {
                "name": "limit",
                "label": "Max Items",
                "type": "number",
                "default": "10000",
            },
        ],
    )

    def connect(self, params: Dict[str, Any]) -> pd.DataFrame:
        import json
        import httpx
        import pandas as pd

        url = params["url"]
        method = params.get("method", "GET").upper()
        headers = json.loads(params.get("headers", "{}") or "{}")
        body = params.get("body", "")
        auth_type = params.get("auth_type", "none")
        auth_value = params.get("auth_value", "")
        data_path = params.get("data_path", "")
        limit = int(params.get("limit", 10000))

        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {auth_value}"
        elif auth_type == "basic":
            import base64

            credentials = base64.b64encode(auth_value.encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        elif auth_type == "api_key":
            headers["X-API-Key"] = auth_value

        request_kwargs = {"url": url, "headers": headers, "timeout": 60}
        if method == "POST" and body:
            request_kwargs["json"] = json.loads(body)

        with httpx.Client() as client:
            if method == "POST":
                response = client.post(**request_kwargs)
            else:
                response = client.get(**request_kwargs)
            response.raise_for_status()
            data = response.json()

        if data_path:
            for key in data_path.split("."):
                if key.isdigit():
                    data = data[int(key)]
                else:
                    data = data.get(key, data)

        if isinstance(data, dict):
            data = [data]
        elif not isinstance(data, list):
            data = [{"value": data}]

        df = pd.DataFrame(data[:limit])
        return df

    def _build_source_string(self, params: Dict[str, Any]) -> str:
        return f"REST API: {params['url']}"


class KafkaConnector(BaseConnector):
    config = ConnectorConfig(
        source_type="kafka",
        name="Apache Kafka",
        description="Stream data from Kafka topics",
        icon="kafka",
        fields=[
            {
                "name": "bootstrap_servers",
                "label": "Bootstrap Servers",
                "type": "text",
                "required": True,
                "placeholder": "localhost:9092",
            },
            {"name": "topic", "label": "Topic", "type": "text", "required": True},
            {
                "name": "group_id",
                "label": "Consumer Group",
                "type": "text",
                "default": "datacove-consumer",
            },
            {
                "name": "offset",
                "label": "Starting Offset",
                "type": "select",
                "options": ["earliest", "latest"],
                "default": "earliest",
            },
            {
                "name": "limit",
                "label": "Message Limit",
                "type": "number",
                "default": "10000",
            },
            {
                "name": "format",
                "label": "Data Format",
                "type": "select",
                "options": ["json", "avro", "csv"],
                "default": "json",
            },
        ],
    )

    def connect(self, params: Dict[str, Any]) -> pd.DataFrame:
        import json
        from kafka import KafkaConsumer
        from kafka.errors import NoBrokersAvailable

        consumer = KafkaConsumer(
            params["topic"],
            bootstrap_servers=params["bootstrap_servers"].split(","),
            group_id=params.get("group_id", "datacove-consumer"),
            auto_offset_reset=params.get("offset", "earliest"),
            enable_auto_commit=True,
            value_deserializer=lambda x: x.decode("utf-8"),
        )

        messages = []
        limit = int(params.get("limit", 10000))
        data_format = params.get("format", "json")

        for i, message in enumerate(consumer):
            if i >= limit:
                break
            try:
                if data_format == "json":
                    record = json.loads(message.value)
                elif data_format == "csv":
                    record = dict(
                        zip(
                            [
                                "field_" + str(j)
                                for j in range(len(message.value.split(",")))
                            ],
                            message.value.split(","),
                        )
                    )
                else:
                    record = {"raw": message.value}
                record["_kafka_partition"] = message.partition
                record["_kafka_offset"] = message.offset
                record["_kafka_timestamp"] = message.timestamp
                messages.append(record)
            except Exception:
                messages.append({"raw": message.value})

        consumer.close()
        return pd.DataFrame(messages)

    def _build_source_string(self, params: Dict[str, Any]) -> str:
        return f"Kafka: {params['bootstrap_servers']}/{params['topic']}"


CONNECTOR_REGISTRY: Dict[str, Type[BaseConnector]] = {
    "postgresql": PostgreSQLConnector,
    "mongodb": MongoDBConnector,
    "snowflake": SnowflakeConnector,
    "bigquery": BigQueryConnector,
    "rest_api": RESTAPIConnector,
    "kafka": KafkaConnector,
}


def get_connector(source_type: str) -> BaseConnector:
    """Get a connector instance by source type."""
    connector_class = CONNECTOR_REGISTRY.get(source_type)
    if not connector_class:
        available = list(CONNECTOR_REGISTRY.keys())
        raise ConnectorNotFoundError(
            f"Unknown connector type: {source_type}. Available: {available}"
        )
    return connector_class()


def list_connectors() -> List[Dict[str, Any]]:
    """List all available connectors with their configurations."""
    return [
        {
            "source_type": c.config.source_type,
            "name": c.config.name,
            "description": c.config.description,
            "icon": c.config.icon,
            "fields": c.config.fields,
        }
        for c in CONNECTOR_REGISTRY.values()
    ]
