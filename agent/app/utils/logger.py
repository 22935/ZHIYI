"""
日志工具 - 统一日志格式和配置
"""
import logging
import sys
from pathlib import Path
from datetime import datetime

# 统一的日志格式
CONSOLE_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
FILE_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# 全局logger实例
_global_logger = None

def setup_logger(name: str = "federal_hub", log_file: str = "logs/federal_hub.log", level: int = logging.INFO):
    """
    设置统一的日志记录器
    
    Args:
        name: 日志记录器名称
        log_file: 日志文件路径
        level: 日志级别
    """
    global _global_logger
    
    # 如果已经创建过全局logger，直接返回
    if _global_logger is not None:
        return _global_logger
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # logger本身设置为DEBUG，由handler控制输出级别
    
    # 避免重复添加handler
    if logger.handlers:
        _global_logger = logger
        return logger
    
    # 创建日志目录
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 文件handler - 记录所有级别的日志
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT)
    file_handler.setFormatter(file_formatter)
    
    # 控制台handler - 只显示INFO及以上级别
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(CONSOLE_FORMAT, datefmt=DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # 防止日志传播到根logger
    logger.propagate = False
    
    _global_logger = logger
    return logger

def get_logger(name: str = None):
    """
    获取logger实例，如果未初始化则先初始化
    
    Args:
        name: 日志记录器名称，如果为None则使用默认名称
    """
    if _global_logger is None:
        return setup_logger(name or "federal_hub")
    
    if name:
        # 返回子logger，继承全局logger的配置
        return logging.getLogger(f"federal_hub.{name}")
    
    return _global_logger

