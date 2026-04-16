FROM python:3.9-slim

RUN mkdir /data
#WORKDIR /data

ADD vrf.py /
#ADD options.json /data

RUN apt-get update && apt-get install -y --no-install-recommends curl
RUN pip3 install requests paho-mqtt==1.6.1

# 最佳实践：安装完系统包后清理缓存，减小镜像体积
RUN rm -rf /var/lib/apt/lists/*

# 组合使用 ENTRYPOINT 和 CMD
#ENTRYPOINT ["python3"]
ENV PATH=/root/.local/bin:$PATH
CMD ["python3","./vrf.py"]
