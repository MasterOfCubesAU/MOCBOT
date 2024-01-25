import requests
from requests.exceptions import HTTPError
import logging
from utils.ConfigHandler import Config

class API:

    BASE_URL = Config.fetch()["API_URL"]
    API_KEY = Config.fetch()["API_KEY"]
    LOGGER = logging.getLogger(__name__)

    def convert_to_int(data):
        if isinstance(data, dict):
            for key in data:
                try:
                    temp = int(data[key])
                except (TypeError, ValueError):
                    continue
                else:
                    data[key] = temp
        elif isinstance(data, list):
            for i, item in enumerate(data):
                try:
                    temp = int(item)
                except (TypeError, ValueError):
                    continue
                else:
                    data[i] = temp
        return data

    @staticmethod
    def post(route: str, body: object):
        try:
            req = requests.post(API.BASE_URL + route, headers={"X-API-KEY": API.API_KEY}, json=body)
            req.raise_for_status()
        except requests.exceptions.HTTPError as err:
            status = err.args[0].split(":")[0]
            raise HTTPError(f"{status}")
        else:
            return API.convert_to_int(req.json())
    
    @staticmethod
    def get(route: str):
        try:
            req = requests.get(API.BASE_URL + route, headers={"X-API-KEY": API.API_KEY})
            req.raise_for_status()
        except requests.exceptions.HTTPError as err:
            status = err.args[0].split(":")[0]
            raise HTTPError(f"{status}", response=err.response)
        else:
            return API.convert_to_int(req.json())
    
    @staticmethod
    def patch(route: str, body: object):
        try:
            req = requests.patch(API.BASE_URL + route, headers={"X-API-KEY": API.API_KEY}, json=body)
            req.raise_for_status()
        except requests.exceptions.HTTPError as err:
            status = err.args[0].split(":")[0]
            raise HTTPError(f"{status}")
        else:
            return API.convert_to_int(req.json())

    @staticmethod
    def put(route: str, body: object):
        try:
            req = requests.put(API.BASE_URL + route, headers={"X-API-KEY": API.API_KEY}, json=body)
            req.raise_for_status()
        except requests.exceptions.HTTPError as err:
            status = err.args[0].split(":")[0]
            raise HTTPError(f"{status}")
        else:
            return API.convert_to_int(req.json())
        
    @staticmethod
    def delete(route: str):
        try:
            req = requests.delete(API.BASE_URL + route, headers={"X-API-KEY": API.API_KEY})
            req.raise_for_status()
        except requests.exceptions.HTTPError as err:
            status = err.args[0].split(":")[0]
            raise HTTPError(f"{status}")
        else:
            return API.convert_to_int(req.json())
        
        