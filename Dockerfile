FROM gorialis/discord.py:master

WORKDIR /app
ADD . /app

RUN pip install -r requirements.txt

CMD ["python", "run.py"]
