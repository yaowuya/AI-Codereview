# 使用官方的 Python 基础镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 配置 pip 使用国内镜像源（清华大学）
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# 安装 supervisord 作为进程管理工具
RUN apt-get update && apt-get install -y --no-install-recommends supervisor \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装依赖（使用国内源，并增加超时时间）
RUN pip install --no-cache-dir -r requirements.txt \
    --timeout 120 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn

RUN mkdir -p log data conf
COPY biz ./biz
COPY fonts ./fonts
COPY api.py ./api.py
COPY ui.py ./ui.py
COPY conf/prompt_templates.yml ./conf/prompt_templates.yml
COPY conf/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# 暴露 Flask 和 Streamlit 的端口
EXPOSE 5001 5002

# 使用 supervisord 作为启动命令
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]