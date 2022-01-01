#!/usr/bin/python3
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
import tenacity
from tenacity import stop_after_attempt, wait_fixed, retry_if_exception_type, RetryCallState
import requests
from requests.exceptions import RequestException
import functools
from decimal import Decimal
from typing import List, Dict
import base64
from pprint import pprint
from settings import user_param
from datetime import datetime, timedelta
from settings import cfg
import os
from utils import plat


class Status:
    Continue = 1
    Stop = 2


class Farmer:
    # wax rpc
    url_rpc = "https://api.wax.alohaeos.com/v1/chain/"
    url_table_row = url_rpc + "get_table_rows"
    # asset API
    url_assets = "https://wax.api.atomicassets.io/atomicassets/v1/assets"
    waxjs: str = None
    myjs: str = None
    chrome_data_dir = os.path.abspath(cfg.chrome_data_dir)

    def __init__(self):
        self.wax_account: str = None
        self.login_name: str = None
        self.password: str = None
        self.driver: webdriver.Chrome = None
        self.http: requests.Session = None
        self.next_operate_time: datetime = datetime.max
        self.next_scan_time: datetime = datetime.min
        self.resoure: Resoure = None
        self.token: Token = None

    def close(self):
        if self.driver:
            self.driver.quit()

    def init(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-extensions")
        options.add_argument("--log-level=3")
        options.add_argument("--disable-logging")
        data_dir = os.path.join(Farmer.chrome_data_dir, self.wax_account)
        options.add_argument("--user-data-dir={0}".format(data_dir))
        self.driver = webdriver.Chrome(plat.driver_path, options=options)
        self.driver.implicitly_wait(60)
        self.driver.set_script_timeout(60)
        self.http = requests.Session()
        self.http.trust_env = False
        self.http.request = functools.partial(self.http.request, timeout=30)

    def inject_waxjs(self):
        if not Farmer.waxjs:
            with open("waxjs.js", "r") as file:
                Farmer.waxjs = file.read()
                file.close()
                Farmer.waxjs = base64.b64encode(Farmer.waxjs.encode()).decode()
        if not Farmer.myjs:
            with open("inject.js", "r") as file:
                Farmer.myjs = file.read()
                file.close()

        code = "var s = document.createElement('script');"
        code += "s.type = 'text/javascript';"
        code += "s.text = atob('{0}');".format(Farmer.waxjs)
        code += "document.head.appendChild(s);"
        self.driver.execute_script(code)
        self.driver.execute_script(Farmer.myjs)
        return True

    def start(self):
        self.driver.get("https://play.farmersworld.io/")
        elem = self.driver.find_element(By.ID, "RPC-Endpoint")
        elem.find_element(By.XPATH, "option[contains(@name, 'https')]")
        wait_seconds = 60
        if self.may_cache_login():
            print("Login with cach")
        else:
            wait_seconds = 600
            print("Please login")
        # find and click login-button
        elem = self.driver.find_element(By.CLASS_NAME, "login-button")
        elem.click()
        elem = self.driver.find_element(By.CLASS_NAME, "login-button--text")
        elem.click()
        WebDriverWait(self.driver, wait_seconds, 1).until(
            EC.presence_of_element_located((By.XPATH, "//img[@class='navbar-group--icon' and @alt='Map']")))
        print("Login successfully")
        time.sleep(cfg.req_interval)
        self.inject_waxjs()
        ret = self.driver.execute_script("return window.wax_login();")

        #get parameters
        print("Loading parameters")
        self.init_farming_config()
        time.sleep(cfg.req_interval)

    def may_cache_login(self):
        cookies = self.driver.execute_cdp_cmd("Network.getCookies", {"urls": ["https://all-access.wax.io"]})
        for item in cookies["cookies"]:
            if item.get("name") == "token_id":
                return True
        return False

    # get tools and plants parameters
    def init_farming_config(self):
        # tools
        post_data = {
            "json": True,
            "code": "farmersworld",
            "scope": "farmersworld",
            "table": "toolconfs",
            "lower_bound": "",
            "upper_bound": "",
            "index_position": 1,
            "key_type": "",
            "limit": 100,
            "reverse": False,
            "show_payer": False
        }
        resp = self.http.post(self.url_table_row, json=post_data)
        resp = resp.json()
        time.sleep(cfg.req_interval)

        # plants
        post_data["table"] = "cropconf"
        resp = self.http.post(self.url_table_row, json=post_data)
        resp = resp.json()

        # membership
        post_data["table"] = "mbsconf"
        resp = self.http.post(self.url_table_row, json=post_data)
        resp = resp.json()

    # scan all functions
    def scan_all(self) -> int:
        status = Status.Continue
        try:
            print("Start new scan")
            time.sleep(cfg.req_interval)

            print("End scan")
            self.next_operate_time = datetime.max
            self.next_scan_time = datetime.now() + cfg.max_scan_interval

            self.next_scan_time = min(self.next_scan_time, self.next_operate_time)

        except Exception as e:
            print("errors, will retry later")
            self.next_scan_time = datetime.now() + cfg.min_scan_interval

        return status

    def run_forever(self):
        while True:
            if datetime.now() > self.next_scan_time:
                status = self.scan_all()
                if status == Status.Stop:
                    self.close()
                    return 1
            time.sleep(1)



def test():
    pass


if __name__ == '__main__':
    test()
