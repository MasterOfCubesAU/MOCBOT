import requests
from requests.exceptions import HTTPError
from lib.bot import config
import logging

class API:

    BASE_URL = "https://api.masterofcubesau.com/v1"
    API_KEY = config["API_KEY"]
    LOGGER = logging.getLogger(__name__)

    @staticmethod
    def convertToInt(data: object):
        for key in data:
            try:
                temp = int(data[key])
            except ValueError:
                continue
            else:
                data[key] = temp
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
            return API.convertToInt(req.json())
    
    @staticmethod
    def get(route: str):
        try:
            req = requests.get(API.BASE_URL + route, headers={"X-API-KEY": API.API_KEY})
            req.raise_for_status()
        except requests.exceptions.HTTPError as err:
            status = err.args[0].split(":")[0]
            raise HTTPError(f"{status}", response=err.response)
        else:
            return API.convertToInt(req.json())
    
    @staticmethod
    def patch(route: str, body: object):
        try:
            req = requests.patch(API.BASE_URL + route, headers={"X-API-KEY": API.API_KEY}, json=body)
            req.raise_for_status()
        except requests.exceptions.HTTPError as err:
            status = err.args[0].split(":")[0]
            raise HTTPError(f"{status}")
        else:
            return API.convertToInt(req.json())

    @staticmethod
    def put(route: str, body: object):
        try:
            req = requests.put(API.BASE_URL + route, headers={"X-API-KEY": API.API_KEY}, json=body)
            req.raise_for_status()
        except requests.exceptions.HTTPError as err:
            status = err.args[0].split(":")[0]
            raise HTTPError(f"{status}")
        else:
            return API.convertToInt(req.json())
        
    @staticmethod
    def delete(route: str):
        try:
            req = requests.delete(API.BASE_URL + route, headers={"X-API-KEY": API.API_KEY})
            req.raise_for_status()
        except requests.exceptions.HTTPError as err:
            status = err.args[0].split(":")[0]
            raise HTTPError(f"{status}")
        else:
            return API.convertToInt(req.json())
        
        