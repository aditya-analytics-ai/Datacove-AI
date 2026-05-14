"""
connector_routes.py - unified data source connectors v2.

POST /api/connectors/import          - generic import via any registered connector
GET  /api/connectors                - list all available connectors with schema
POST /api/connectors/validate       - validate connector params without importing
POST /api/connectors/test/{type}    - test connection without importing data

Available connectors:
  - postgresql: PostgreSQL database
  - mongodb: MongoDB collection
  - snowflake: Snowflake data warehouse
  - bigquery: Google BigQuery
  - rest_api: Any REST API endpoint
  - kafka: Apache Kafka streaming (batch mode)
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from models.dataset_session import DatasetSession, save_session
from services.connectors import get_connector, list_connectors, CONNECTOR_REGISTRY
from utils.auth import get_current_user, AuthUser
from utils.logger import logger
from utils.errors import ConnectorValidationError, ConnectorNotFoundError

router = APIRouter(dependencies=[Depends(get_current_user)])


class GenericImportRequest(BaseModel):
    source_type: str = Field(
        ..., description="Connector type (postgresql, mongodb, etc.)"
    )
    params: Dict[str, Any] = Field(..., description="Connector-specific parameters")
    filename: Optional[str] = Field(
        None, description="Optional filename for the session"
    )


class ValidateConnectorRequest(BaseModel):
    source_type: str
    params: Dict[str, Any]


@router.get("/connectors")
def get_available_connectors():
    """List all available data source connectors with their configuration schemas."""
    connectors = list_connectors()

    available = {}
    for source_type in CONNECTOR_REGISTRY:
        try:
            get_connector(source_type)
            available[source_type] = True
        except ImportError:
            available[source_type] = False

    return JSONResponse(
        {
            "connectors": connectors,
            "availability": available,
        }
    )


@router.post("/connectors/validate")
async def validate_connector(
    req: ValidateConnectorRequest, user: AuthUser = Depends(get_current_user)
):
    """Validate connector parameters without importing data."""
    try:
        connector = get_connector(req.source_type)
        connector.validate_params(req.params)

        def _test():
            return connector.connect(req.params)

        df = await run_in_threadpool(_test)

        return JSONResponse(
            {
                "valid": True,
                "source_type": req.source_type,
                "preview_rows": min(5, len(df)),
                "preview": df.head(5).to_dict(orient="records") if len(df) > 0 else [],
                "columns": list(df.columns),
                "total_rows": len(df),
            }
        )
    except ImportError as e:
        raise HTTPException(
            status_code=501,
            detail=f"Connector '{req.source_type}' not available: {e}. Install required packages.",
        )
    except ConnectorValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ConnectorNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Connection failed: {e}")


@router.post("/connectors/test/{source_type}")
async def test_connector(
    source_type: str, params: Dict[str, Any], user: AuthUser = Depends(get_current_user)
):
    """Test a specific connector without importing data. Returns success/failure."""
    try:
        connector = get_connector(source_type)

        def _test():
            return connector.connect(params)

        df = await run_in_threadpool(_test)

        return JSONResponse(
            {
                "success": True,
                "source_type": source_type,
                "rows_available": len(df),
                "columns": list(df.columns) if len(df) > 0 else [],
                "sample": df.head(3).to_dict(orient="records") if len(df) > 0 else [],
            }
        )
    except ImportError as e:
        raise HTTPException(
            status_code=501,
            detail=f"Connector '{source_type}' requires additional packages: {e}",
        )
    except (ConnectorValidationError, ConnectorNotFoundError) as e:
        return JSONResponse(
            {
                "success": False,
                "source_type": source_type,
                "error": str(e),
            }
        )
    except Exception as e:
        return JSONResponse(
            {
                "success": False,
                "source_type": source_type,
                "error": str(e),
            }
        )


@router.post("/connectors/import")
async def import_from_connector(
    req: GenericImportRequest, user: AuthUser = Depends(get_current_user)
):
    """
    Import data from any registered connector.

    Supported source_types:
      - postgresql: PostgreSQL database
      - mongodb: MongoDB collection
      - snowflake: Snowflake data warehouse
      - bigquery: Google BigQuery
      - rest_api: Any REST API endpoint
      - kafka: Apache Kafka (batch)
    """
    try:
        connector = get_connector(req.source_type)

        def _load():
            connector.validate_params(req.params)
            df = connector.connect(req.params)
            filename = req.filename
            if filename is None:
                filename = (
                    f"{connector.config.name}_"
                    f"{req.params.get('table', req.params.get('collection', 'import'))}.csv"
                )
            preview = safe_preview(df)
            return df, filename, preview

        df, filename, preview = await run_in_threadpool(_load)

        session_id = str(uuid.uuid4())
        session = DatasetSession(df=df, filename=filename, owner_id=user.user_id)
        save_session(session_id, session)

        logger.info(
            f"Connector import: {req.source_type} → session={session_id} "
            f"({len(df)} rows)"
        )

        return JSONResponse(
            {
                "session_id": session_id,
                "filename": filename,
                "source": connector._build_source_string(req.params),
                "rows": len(df),
                "columns": list(df.columns),
                "preview": preview,
                "metadata": {"source_type": connector.config.source_type},
            }
        )

    except ImportError as e:
        raise HTTPException(
            status_code=501,
            detail=f"Connector '{req.source_type}' not available. Install required packages: {e}",
        )
    except ConnectorValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ConnectorNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Connector import failed ({req.source_type}): {e}")
        raise HTTPException(status_code=422, detail=f"Import failed: {e}")


# ── Convenience endpoints for individual connectors ─────────────────────────────


class PostgreSQLImportRequest(BaseModel):
    host: str
    port: int = 5432
    database: str
    db_schema: str = "public"
    username: str
    password: str
    query: Optional[str] = None
    table: Optional[str] = None
    limit: int = 100000


@router.post("/connectors/postgresql")
async def import_postgresql(
    req: PostgreSQLImportRequest, user: AuthUser = Depends(get_current_user)
):
    """Import data directly from PostgreSQL."""
    return await import_from_connector(
        GenericImportRequest(
            source_type="postgresql",
            params=req.model_dump(),
        ),
        user,
    )


class MongoDBImportRequest(BaseModel):
    connection_string: str
    database: str
    collection: str
    query: str = "{}"
    projection: str = "{}"
    limit: int = 10000


@router.post("/connectors/mongodb")
async def import_mongodb(
    req: MongoDBImportRequest, user: AuthUser = Depends(get_current_user)
):
    """Import data directly from MongoDB."""
    return await import_from_connector(
        GenericImportRequest(
            source_type="mongodb",
            params=req.model_dump(),
        ),
        user,
    )


class RESTAPIImportRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: str = '{"Content-Type": "application/json"}'
    body: Optional[str] = None
    auth_type: str = "none"
    auth_value: str = ""
    data_path: str = ""
    limit: int = 10000


@router.post("/connectors/rest_api")
async def import_rest_api(
    req: RESTAPIImportRequest, user: AuthUser = Depends(get_current_user)
):
    """Import data from any REST API."""
    return await import_from_connector(
        GenericImportRequest(
            source_type="rest_api",
            params=req.model_dump(),
        ),
        user,
    )


class SnowflakeImportRequest(BaseModel):
    account: str
    username: str
    password: str
    warehouse: str
    database: str
    db_schema: str = "PUBLIC"
    query: Optional[str] = None
    table: Optional[str] = None
    limit: int = 100000


@router.post("/connectors/snowflake")
async def import_snowflake(
    req: SnowflakeImportRequest, user: AuthUser = Depends(get_current_user)
):
    """Import data directly from Snowflake."""
    return await import_from_connector(
        GenericImportRequest(
            source_type="snowflake",
            params=req.model_dump(),
        ),
        user,
    )


class BigQueryImportRequest(BaseModel):
    credentials_json: str
    project_id: str
    query: Optional[str] = None
    table: Optional[str] = None
    limit: int = 100000


@router.post("/connectors/bigquery")
async def import_bigquery(
    req: BigQueryImportRequest, user: AuthUser = Depends(get_current_user)
):
    """Import data directly from Google BigQuery."""
    return await import_from_connector(
        GenericImportRequest(
            source_type="bigquery",
            params=req.model_dump(),
        ),
        user,
    )
