"""个人量化工具箱，通过 Python 包接口使用。"""

from loguru import logger

# 库不替宿主决定日志: 默认关闭本包输出, 避免污染使用方的 stderr
# (loguru 官方对库的建议就是 disable)。需要排查问题时, 在 import 之后显式打开:
#     from loguru import logger
#     logger.enable("quanttoolskit")
logger.disable("quanttoolskit")
