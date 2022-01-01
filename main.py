#!/usr/bin/python3
from farmer import Farmer
import yaml
import sys
from settings import load_user_param, user_param

def run(config_file: str):
    with open(config_file, "r", encoding="utf8") as file:
        user: dict = yaml.load(file, Loader=yaml.FullLoader)
        file.close()
    load_user_param(user)
    farmer = Farmer()
    farmer.wax_account = user_param.wax_account
    farmer.init()
    farmer.start()
    print("start farming")
    return farmer.run_forever()


def main():
    try:
        user_yml = "user.yml"
        run(user_yml)
    except Exception:
        print("An exception occured")
    input()

if __name__ == '__main__':
    main()
