from dataclasses import dataclass
from datetime import timedelta

@dataclass
class Settings:
    path_logs: str
    chrome_data_dir: str
    url_db: str = None
    # interval for http requests
    req_interval = 3
    # scan at least 1 time in 1 hour
    max_scan_interval = timedelta(minutes=15)
    # scan intervals, even if errors
    min_scan_interval = timedelta(seconds = 10)


# configuration by user
class user_param:
    wax_account: str = None

    mining: bool = True
    plant: bool = True
    mbs: bool = True
    recover_energy: int = 500

    @staticmethod
    def to_dict():
        return {
            "wax_account": user_param.wax_account,
            "mining": user_param.mining,
            "plant": user_param.plant,
            "mbs": user_param.mbs,
            "recover_energy": user_param.recover_energy,
        }


def load_user_param(user: dict):
    user_param.wax_account = user["wax_account"]
    user_param.mining = user.get("mining", True)
    user_param.plant = user.get("plant", True)
    user_param.mbs = user.get("mbs", True)
    user_param.recover_energy = user.get("recover_energy", 500)


cfg = Settings(
    path_logs="./logs/",
    chrome_data_dir="./data_dir/",
)

