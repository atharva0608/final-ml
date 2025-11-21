"""
Database utilities for Spot Optimizer backend
Shared database connection pooling and query execution
"""

import os
import logging
from typing import Any
import mysql.connector
from mysql.connector import Error, pooling

logger = logging.getLogger(__name__)

# ==============================================================================
# DATABASE CONFIGURATION
# ==============================================================================

class DatabaseConfig:
    """Database configuration with environment variable support"""
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', 3306))
    DB_USER = os.getenv('DB_USER', 'spotuser')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'SpotUser2024!')
    DB_NAME = os.getenv('DB_NAME', 'spot_optimizer')
    DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', 10))

db_config = DatabaseConfig()

# ==============================================================================
# DATABASE CONNECTION POOLING
# ==============================================================================

connection_pool = None

def init_db_pool():
    """Initialize database connection pool"""
    global connection_pool
    try:
        logger.info(f"Initializing database pool: {db_config.DB_USER}@{db_config.DB_HOST}:{db_config.DB_PORT}/{db_config.DB_NAME}")
        connection_pool = pooling.MySQLConnectionPool(
            pool_name="spot_optimizer_pool",
            pool_size=db_config.DB_POOL_SIZE,
            pool_reset_session=True,
            host=db_config.DB_HOST,
            port=db_config.DB_PORT,
            user=db_config.DB_USER,
            password=db_config.DB_PASSWORD,
            database=db_config.DB_NAME,
            autocommit=False
        )

        # Test the connection
        test_conn = connection_pool.get_connection()
        test_conn.close()

        logger.info(f"✓ Database connection pool initialized (size: {db_config.DB_POOL_SIZE})")
        return True
    except Error as e:
        logger.error(f"Failed to initialize connection pool: {e}")
        logger.error(f"Connection details: {db_config.DB_USER}@{db_config.DB_HOST}:{db_config.DB_PORT}/{db_config.DB_NAME}")
        return False

def get_db_connection():
    """Get connection from pool"""
    global connection_pool

    # Initialize pool if not already done
    if connection_pool is None:
        init_db_pool()

    try:
        return connection_pool.get_connection()
    except Error as e:
        logger.error(f"Failed to get connection from pool: {e}")
        raise

def execute_query(query: str, params: tuple = None, fetch: bool = False,
                 fetch_one: bool = False, commit: bool = True) -> Any:
    """
    Execute database query with error handling

    Args:
        query: SQL query string
        params: Query parameters (tuple)
        fetch: Whether to fetch all results
        fetch_one: Whether to fetch single result
        commit: Whether to commit transaction

    Returns:
        Query results or affected row count
    """
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params or ())

        if fetch_one:
            result = cursor.fetchone()
        elif fetch:
            result = cursor.fetchall()
        else:
            result = cursor.lastrowid if cursor.lastrowid else cursor.rowcount

        if commit and not fetch and not fetch_one:
            connection.commit()

        return result
    except Error as e:
        if connection:
            connection.rollback()
        logger.error(f"Query execution error: {e}")
        logger.error(f"Query: {query[:200]}")
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
