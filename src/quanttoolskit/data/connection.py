"""对 DuckDB 数据库做链接"""

from __future__ import annotations

from pathlib import Path

import duckdb
from loguru import logger


def get_duckdb(
        *, 
        path: Path, 
        read_only: bool = True
        ) -> duckdb.DuckDBPyConnection:
    """
    连接 DuckDB 数据库
    
    Args:
        path: 数据库文件的绝对路径 (Path对象)
        read_only: 是否以只读模式打开 (默认True防止回测时意外修改数据)

    Returns:
        duckdb.DuckDBPyConnection: 数据库连接对象
    """
    if not path.exists():
        logger.error(f"数据库文件不存在: {path}")
        raise FileNotFoundError(f"Database file not found at {path}")

    logger.debug(f"正在连接 DuckDB: {path} (read_only = {read_only})")
    return duckdb.connect(str(path), read_only=read_only)