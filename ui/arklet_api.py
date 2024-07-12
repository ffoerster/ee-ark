import requests
import csv
import argparse
import json
import os

# DEFAULT_URL = 'http://127.0.0.1:8001'
DEFAULT_URL = "http://ark.frick.org:8080"
DEFAULT_KEY = os.environ["ARK_API_KEY"]

MINT_FIELDS = [
    "naan",
    "shoulder",
    "url",
    "metadata",
    "title",
    "type",
    "commitment",
    "identifier",
    "format",
    "relation",
    "source",
    "csv",
]

UPDATE_FIELDS = MINT_FIELDS + ["ark"]

GET = "get"
POST = "post"
PUT = "put"


class ArkAPIError(Exception):
    pass


def query_generic(method, url, **kwargs):
    url = DEFAULT_URL + "/" + url
    if method == GET:
        response = requests.get(url, timeout=5)  # Timeout in seconds
    elif method == POST:
        response = requests.post(url, timeout=5, **kwargs)
    elif method == PUT:
        response = requests.put(url, timeout=5, **kwargs)
    if response.status_code == 200:
        return response.json()
    else:
        raise ArkAPIError(f"Request failed: {response.status_code}, {response.text}")


def query(data):
    if "ark" not in data or not data["ark"]:
        raise ValueError("Must include --ark argument")
    return query_generic(GET, data["ark"] + "?json")


def status(_):
    return query_generic(GET, "")


def authorized(method, url, data):
    auth = DEFAULT_KEY
    return query_generic(method, url, json=data, headers={"Authorization": auth})


def update(data: dict):
    if "ark" not in data or not data["ark"]:
        raise ValueError("Must include --ark argument")
    return authorized(PUT, "update", data)


def mint(data: dict):
    if "naan" not in data or not data["naan"]:
        raise ValueError("Must include --naan argument for mint operation")
    if "shoulder" not in data or not data["shoulder"]:
        raise ValueError("Must include --shoulder argument for mint operation")
    return authorized(POST, "mint", data)


def csv2json(csvfile):
    reader = csv.DictReader(open(csvfile, "rt"))
    return [r for r in reader]


def query_csv(data: dict):
    if "csv" not in data or not data["csv"]:
        raise ValueError("Must include --csv argument for bulk operations")
    if len(data.keys()) != 1:
        raise ValueError("Only --csv argument is required for bulk query")
    jsondata = csv2json(data["csv"])
    if "ark" not in jsondata[0]:
        raise ValueError("CSV for bulk ark querying must include 'ark' column")
    return query_generic(POST, "bulk_query", json=jsondata)


def update_csv(data: dict):
    if "csv" not in data or not data["csv"]:
        raise ValueError("Must include --csv argument for bulk operations")
    if len(data.keys()) != 1:
        raise ValueError("Only --csv argument is required for bulk update")
    update_data = csv2json(data["csv"])
    for record in update_data:
        if "ark" not in record:
            raise ValueError("CSV for bulk ark updating must include 'ark' column")
    return authorized(
        POST,
        "bulk_update",
        {
            "data": update_data,
        },
    )


ﬂ


def mint_csv(data: dict):
    if "csv" not in data or not data["csv"]:
        raise ValueError("Must include --csv argument for bulk operations")
    if "naan" not in data or not data["naan"]:
        raise ValueError("Must include --naan argument for bulk operations")
    if len(data.keys()) != 2:
        raise ValueError("Only --csv and --naan arguments are required for bulk mint")
    mint_data = csv2json(data["csv"])
    return authorized(POST, "bulk_mint", {"data": mint_data, "naan": data["naan"]})


ENDPOINTS = [query, update, mint, query_csv, update_csv, mint_csv, status]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ARK API command line suite")
    parser.add_argument(
        "action",
        help="API Action you wish to execute",
        choices=[f.__name__ for f in ENDPOINTS],
    )
    for f in UPDATE_FIELDS:
        parser.add_argument(f"--{f}", help=f)

    args = parser.parse_args()
    action_func = locals()[args.action]
    result = action_func(vars(args))
    print(json.dumps(result, indent=4))
