FROM python:3.7-alpine

RUN mkdir /data
#WORKDIR /data

ADD vrf.py /
ADD options.json /data

RUN apk update
RUN pip3 install requests paho-mqtt==1.6.1

# 组合使用 ENTRYPOINT 和 CMD
#ENTRYPOINT ["python3"]
ENV PATH=/root/.local/bin:$PATH
CMD ["python3","./vrf.py"]
