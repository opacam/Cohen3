FROM python:3.8.2-slim as build
RUN apt-get -yqq update && apt-get -yqq install git build-essential && ldconfig
ADD . /cohen3
RUN mkdir /wheels && cd /wheels && pip wheel /cohen3

FROM python:3.8.2-slim as run
COPY --from=build /wheels /wheels
RUN cd /wheels && pip install *
ADD misc/cohen3.conf.example /cohen3/cohen3.conf
VOLUME [/config]

CMD cohen3 --configfile=/config/cohen3.conf
