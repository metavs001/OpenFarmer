#!/usr/bin/python3
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
import tenacity
from tenacity import stop_after_attempt, wait_fixed, retry_if_exception_type, RetryCallState
import logging
import requests
from requests.exceptions import RequestException
import functools
from decimal import Decimal
from typing import List, Dict
import base64
from pprint import pprint
import logger
import utils
from utils import plat
from settings import user_param
import res
from res import Building, Resoure, Animal, Asset, Farming, Crop, NFT, Axe, Tool, Token, Chicken, FishingRod, MBS
from datetime import datetime, timedelta
from settings import cfg
import os
from logger import log

class FarmerException(Exception):
    pass


class CookieExpireException(FarmerException):
    pass


# 调用智能合约出错，此时应停止并检查日志，不宜反复重试
class TransactException(FarmerException):
    # 有的智能合约错误可以重试,-1为无限重试
    def __init__(self, msg, retry=True, max_retry_times: int = -1):
        super().__init__(msg)
        self.retry = retry
        self.max_retry_times = max_retry_times


# 遇到不可恢复的错误 ,终止程序
class StopException(FarmerException):
    pass


class Status:
    Continue = 1
    Stop = 2


class Farmer:
    # wax rpc
    url_rpc = "https://api.wax.alohaeos.com/v1/chain/"
    url_table_row = url_rpc + "get_table_rows"
    # 资产API
    url_assets = "https://wax.api.atomicassets.io/atomicassets/v1/assets"
    waxjs: str = None
    myjs: str = None
    chrome_data_dir = os.path.abspath(cfg.chrome_data_dir)

    def __init__(self):
        self.wax_account: str = None
        self.login_name: str = None
        self.password: str = None
        self.driver: webdriver.Chrome = None
        self.proxy: str = None
        self.http: requests.Session = None
        self.cookies: List[dict] = None
        self.log: logging.LoggerAdapter = log
        # 下一次可以操作东西的时间
        self.next_operate_time: datetime = datetime.max
        # 下一次扫描时间
        self.next_scan_time: datetime = datetime.min
        # 本轮扫描中暂不可操作的东西
        self.not_operational: List[Farming] = []
        # 智能合约连续出错次数
        self.count_error_transact = 0
        # 本轮扫描中作物操作成功个数
        self.count_success_claim = 0
        # 本轮扫描中作物操作失败个数
        self.count_error_claim = 0
        # 本轮开始时的资源数量
        self.resoure: Resoure = None
        self.token: Token = None

    def close(self):
        if self.driver:
            self.log.info("稍等，程序正在退出")
            self.driver.quit()

    def init(self):
        self.log.extra["tag"] = self.wax_account
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-extensions")
        options.add_argument("--log-level=3")
        options.add_argument("--disable-logging")
        data_dir = os.path.join(Farmer.chrome_data_dir, self.wax_account)
        options.add_argument("--user-data-dir={0}".format(data_dir))
        if self.proxy:
            options.add_argument("--proxy-server={0}".format(self.proxy))
        self.driver = webdriver.Chrome(plat.driver_path, options=options)
        self.driver.implicitly_wait(60)
        self.driver.set_script_timeout(60)
        self.http = requests.Session()
        self.http.trust_env = False
        self.http.request = functools.partial(self.http.request, timeout=30)
        if self.proxy:
            self.http.proxies = {
                "http": "http://{0}".format(self.proxy),
                "https": "http://{0}".format(self.proxy),
            }
        http_retry_wrapper = tenacity.retry(wait=wait_fixed(cfg.req_interval), stop=stop_after_attempt(5),
                                            retry=retry_if_exception_type(RequestException),
                                            before_sleep=self.log_retry, reraise=True)
        self.http.get = http_retry_wrapper(self.http.get)
        self.http.post = http_retry_wrapper(self.http.post)

    def inject_waxjs(self):
        # 如果已经注入过就不再注入了
        if self.driver.execute_script("return window.mywax != undefined;"):
            return True

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
        self.log.info("启动浏览器")
        if self.cookies:
            self.log.info("使用预设的cookie自动登录")
            cookies = self.cookies["cookies"]
            key_cookie = {}
            for item in cookies:
                if item.get("domain") == "all-access.wax.io":
                    key_cookie = item
                    break
            if not key_cookie:
                raise CookieExpireException("not find cookie domain as all-access.wax.io")
            ret = self.driver.execute_cdp_cmd("Network.setCookie", key_cookie)
            self.log.info("Network.setCookie: {0}".format(ret))
            if not ret["success"]:
                raise CookieExpireException("Network.setCookie error")
        self.driver.get("https://play.farmersworld.io/")
        # 等待页面加载完毕
        elem = self.driver.find_element(By.ID, "RPC-Endpoint")
        elem.find_element(By.XPATH, "option[contains(@name, 'https')]")
        wait_seconds = 60
        if self.may_cache_login():
            self.log.info("使用Cache自动登录")
        else:
            wait_seconds = 600
            self.log.info("请在弹出的窗口中手动登录账号")
        # 点击登录按钮，点击WAX云钱包方式登录
        elem = self.driver.find_element(By.CLASS_NAME, "login-button")
        elem.click()
        elem = self.driver.find_element(By.CLASS_NAME, "login-button--text")
        elem.click()
        # 等待登录成功
        self.log.info("等待登录")
        WebDriverWait(self.driver, wait_seconds, 1).until(
            EC.presence_of_element_located((By.XPATH, "//img[@class='navbar-group--icon' and @alt='Map']")))
        # self.driver.find_element(By.XPATH, "//img[@class='navbar-group--icon' and @alt='Map']")
        self.log.info("登录成功,稍等...")
        time.sleep(cfg.req_interval)
        self.inject_waxjs()
        ret = self.driver.execute_script("return window.wax_login();")
        self.log.info("window.wax_login(): {0}".format(ret))
        if not ret[0]:
            raise CookieExpireException("cookie失效")

        # 从服务器获取游戏参数
        self.log.info("正在加载游戏配置")
        self.init_farming_config()
        time.sleep(cfg.req_interval)

    def may_cache_login(self):
        cookies = self.driver.execute_cdp_cmd("Network.getCookies", {"urls": ["https://all-access.wax.io"]})
        for item in cookies["cookies"]:
            if item.get("name") == "token_id":
                return True
        return False

    def log_retry(self, state: RetryCallState):
        exp = state.outcome.exception()
        if isinstance(exp, RequestException):
            self.log.info("网络错误: {0}".format(exp))
            self.log.info("正在重试: [{0}]".format(state.attempt_number))

    def table_row_template(self) -> dict:
        post_data = {
            "json": True,
            "code": "farmersworld",
            "scope": "farmersworld",
            "table": None,  # 覆写
            "lower_bound": self.wax_account,
            "upper_bound": self.wax_account,
            "index_position": None,  # 覆写
            "key_type": "i64",
            "limit": 100,
            "reverse": False,
            "show_payer": False
        }
        return post_data

    # 从服务器获取各种工具和作物的参数
    def init_farming_config(self):
        # 工具
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
        self.log.debug("get tools config:{0}".format(resp.text))
        resp = resp.json()
        res.init_tool_config(resp["rows"])
        time.sleep(cfg.req_interval)

        # 农作物
        post_data["table"] = "cropconf"
        resp = self.http.post(self.url_table_row, json=post_data)
        self.log.debug("get crop config:{0}".format(resp.text))
        resp = resp.json()
        res.init_crop_config(resp["rows"])

        # 会员卡
        post_data["table"] = "mbsconf"
        resp = self.http.post(self.url_table_row, json=post_data)
        self.log.debug("get mbs config:{0}".format(resp.text))
        resp = resp.json()
        res.init_mbs_config(resp["rows"])

    # 获取wax账户信息
    def wax_get_account(self):
        url = self.url_rpc + "get_account"
        post_data = {"account_name": self.wax_account}
        resp = self.http.post(url, json=post_data)
        self.log.debug("get_account:{0}".format(resp.text))
        resp = resp.json()
        return resp

    # 签署交易(只许成功，否则抛异常）
    def wax_transact(self, transaction: dict):
        self.inject_waxjs()
        self.log.info("begin transact: {0}".format(transaction))
        try:
            success, result = self.driver.execute_script("return window.wax_transact(arguments[0]);", transaction)
            if success:
                self.log.info("transact ok, transaction_id: [{0}]".format(result["transaction_id"]))
                self.log.debug("transact result: {0}".format(result))
                return True
            else:
                self.log.error("transact error: {0}".format(result))
                if "is greater than the maximum billable" in result:
                    self.log.error("EOS CPU资源不足，可能需要质押更多WAX，一般为误报，稍后重试")
                    raise TransactException(result)
                raise TransactException(result)
        except WebDriverException as e:
            self.log.error("transact error: {0}".format(e))
            self.log.exception(str(e))
            raise TransactException(result)

    # 过滤可操作的作物
    def filter_operable(self, items: List[Farming]) -> Farming:
        now = datetime.now()
        op = []
        for item in items:
            if isinstance(item, Building):
                if item.is_ready == 1:
                    continue
            # 鸡24小时内最多喂4次
            if isinstance(item, Chicken):
                if len(item.day_claims_at) >= 4:
                    next_op_time = item.day_claims_at[0] + timedelta(hours=24)
                    item.next_availability = max(item.next_availability, next_op_time)
            if now < item.next_availability:
                self.not_operational.append(item)
                continue
            op.append(item)
        return op

    def reset_before_scan(self):
        self.not_operational.clear()
        self.count_success_claim = 0
        self.count_error_claim = 0

    # 检查正在培养的作物， 返回值：是否继续运行程序
    def scan_all(self) -> int:
        status = Status.Continue
        try:
            self.reset_before_scan()
            self.log.info("开始一轮扫描")
            time.sleep(cfg.req_interval)

            self.log.info("结束一轮扫描")
            if self.not_operational:
                self.next_operate_time = min([item.next_availability for item in self.not_operational])
                self.log.info("下一次可操作时间: {0}".format(utils.show_time(self.next_operate_time)))
                # 可操作时间到了，也要延后5秒再扫，以免
                self.next_operate_time += timedelta(seconds=5)
            else:
                self.next_operate_time = datetime.max
            if self.count_success_claim > 0 or self.count_error_claim > 0:
                self.log.info(f"本轮操作成功数量: {self.count_success_claim} 操作失败数量: {self.count_error_claim}")

            if self.count_error_claim > 0:
                self.log.info("本轮有失败操作，稍后重试")
                self.next_scan_time = datetime.now() + cfg.min_scan_interval
            else:
                self.next_scan_time = datetime.now() + cfg.max_scan_interval

            self.next_scan_time = min(self.next_scan_time, self.next_operate_time)

            # 没有合约出错，清空错误计数器
            self.count_error_transact = 0

        except TransactException as e:
            self.log.exception("智能合约调用出错")
            if not e.retry:
                return Status.Stop
            self.count_error_transact += 1
            self.log.error("合约调用异常【{0}】次".format(self.count_error_transact))
            if self.count_error_transact >= e.max_retry_times and e.max_retry_times != -1:
                self.log.error("合约连续调用异常")
                return Status.Stop
            self.next_scan_time = datetime.now() + cfg.min_scan_interval
        except CookieExpireException as e:
            self.log.exception(str(e))
            self.log.error("Cookie失效，请手动重启程序并重新登录")
            return Status.Stop
        except StopException as e:
            self.log.exception(str(e))
            self.log.error("不可恢复错误，请手动处理，然后重启程序并重新登录")
            return Status.Stop
        except FarmerException as e:
            self.log.exception(str(e))
            self.log.error("常规错误，稍后重试")
            self.next_scan_time = datetime.now() + cfg.min_scan_interval
        except Exception as e:
            self.log.exception(str(e))
            self.log.error("常规错误，稍后重试")
            self.next_scan_time = datetime.now() + cfg.min_scan_interval

        self.log.info("下一轮扫描时间: {0}".format(utils.show_time(self.next_scan_time)))
        return status

    def run_forever(self):
        while True:
            if datetime.now() > self.next_scan_time:
                status = self.scan_all()
                if status == Status.Stop:
                    self.close()
                    self.log.info("程序已停止，请检查日志后手动重启程序")
                    return 1
            time.sleep(1)



def test():
    pass


if __name__ == '__main__':
    test()
