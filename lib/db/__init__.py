import mysql.connector as mysql
from mysql.connector import errorcode
import yaml
import logging

with open("./config.yml", "r") as f:
    config = yaml.safe_load(f)

class MOC_DB:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def connect(self):
        try:
            self.connection = mysql.connect(user=config["DATABASE"]["USER"], password=config["DATABASE"]["PASS"], host=config["DATABASE"]["HOST"], database=config["DATABASE"]["DB_NAME"], autocommit=True)
        except mysql.Error as err:
            if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                self.logger.error("[DB] Database credentials incorrect.")
            elif err.errno == errorcode.ER_BAD_DB_ERROR:
                self.logger.error("[DB] Database does not exist.")
            else:
                self.logger.error(f"[DB] {err}")
        else:
            self.cursor = self.connection.cursor(buffered=True)
            self.logger.info("[DB] Connection established.")

    def execute(self, command, *values):
        self.cursor.execute(command, tuple(values))

    def field(self, command, *values):
        self.cursor.execute(command, tuple(values))
        fetch = self.cursor.fetchone()
        if fetch is not None:
            return fetch[0]
        return None

    def record(self, command, *values):
        self.cursor.execute(command, tuple(values))
        return self.cursor.fetchone()

    def records(self, command, *values):
        self.cursor.execute(command, tuple(values))
        return self.cursor.fetchall()

    def column(self, command, *values):
        self.cursor.execute(command, tuple(values))
        return [item[0] for item in self.cursor.fetchall()]


