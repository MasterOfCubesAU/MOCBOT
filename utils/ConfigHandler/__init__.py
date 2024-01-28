import logging
import yaml


class Config:
    CONFIG_FILENAME = "./config.yml"
    LOGGER = logging.getLogger(__name__)

    CONFIG = {}

    @staticmethod
    def fetch():
        if not Config.CONFIG:
            try:
                with open(Config.CONFIG_FILENAME, "r") as f:
                    Config.CONFIG = yaml.safe_load(f)
            except IOError:
                Config.LOGGER.error("Could not find a config file. Please see the README.md for setup instructions")

        return Config.CONFIG
