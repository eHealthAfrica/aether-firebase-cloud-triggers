FROM python:3.7-slim-buster
RUN mkdir /test
WORKDIR /test
COPY ./test/conf/requirements.txt /test/requirements.txt
RUN pip install -q --upgrade pip && \
    pip install -q -r /test/requirements.txt
COPY ./test/* /test/
COPY ./*.py /test/