"""
API 服务主程序入口
"""
from dotenv import load_dotenv

# 必须在其他导入之前加载环境变量
load_dotenv("conf/.env")

import os

from biz.api import api_app, init_app
from biz.api.scheduler import setup_scheduler
from biz.utils.config_checker import check_config

# 初始化应用并注册路由
init_app(api_app)

# 模块级初始化：flask run 和 python api.py 两种方式均生效
check_config()
setup_scheduler()

if __name__ == '__main__':
    # 启动Flask API服务
    port = int(os.environ.get('SERVER_PORT', 5001))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    api_app.run(host='0.0.0.0', port=port, debug=debug)
