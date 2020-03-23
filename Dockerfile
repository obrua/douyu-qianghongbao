# FROM python:3.7-alpine as apy
FROM python:3.7 as apy
WORKDIR /code 
COPY . /code 
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ \ 
    && pip --no-cache-dir install -r requirements.txt
CMD ["python", "run_main.py"]

