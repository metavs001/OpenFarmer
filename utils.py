import psutil
from datetime import datetime
import platform
from typing import List
import shutil
import os

def show_time(t):
    if isinstance(t, datetime):
        return t.strftime('%Y-%m-%d %H:%M:%S')
    else:
        return datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M:%S')


class plat:
    name: str = None
    chromedriver: str = None
    python: str = None
    python_path: str = None
    driver_path:str =None


if platform.system().lower() == "windows":
    plat.name = "windows"
    plat.chromedriver = "chromedriver.exe"
    plat.python = "python.exe"
elif platform.system().lower() == "linux":
    plat.name = "linux"
    plat.chromedriver = "chromedriver"
    plat.python = "python3"
elif platform.system().lower() == "darwin":
    plat.name = "macos"
    plat.chromedriver = "chromedriver"
    plat.python = "python3"
plat.python_path = shutil.which(plat.python)
plat.driver_path = shutil.which(plat.chromedriver)
if not plat.driver_path:
    plat.driver_path = os.path.join(os.path.split(os.path.realpath(__file__))[0], plat.chromedriver)

if __name__ == '__main__':
    test()
    print(plat.python_path)
