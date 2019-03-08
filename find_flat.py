#!/usr/bin/env python3

import sys
import time
import re
import os
from multiprocessing import Pool

import requests
from bs4 import BeautifulSoup

MAX_PAGES = 42
OFFERS_PER_PAGE = 35
POOL_SIZE = int(os.environ.get("POOL_SIZE", OFFERS_PER_PAGE))

RESULTS_FILE = "flats_id.list"

SEARCH_URL = "https://www.leboncoin.fr/recherche/?" \
    + "&".join([
        "category=10",  # locations
        "locations=Paris",
        "real_estate_type=2",  # appart
        "price=600-800",
        "square=20-max",
        "furnished=1",  # meublé
        # "rooms=2",
        "page={}"
    ])
OFFER_URL = "https://www.leboncoin.fr/locations/{}.htm/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:65.0) "
    + "Gecko/20100101 Firefox/65.0",
    "Accept": "text/html",
    "Accept-Language": "en-US",
    "Accept-Encoding": "identity"
}


# IO #
def read_flats_id():
    with open("flats_id.list", mode="r") as f:
        flats_id = [line.rstrip('\n') for line in f]
    return flats_id


def handle_results(results):
    # print(results, len(results))  # DEBUG
    with open("flats_id.list", mode="a") as f:
        print("\n".join(results), file=f)
    for offer_id in results:
        os.system("firefox " + OFFER_URL.format(offer_id))


# REQUESTS #

def get_url_content(url):
    while True:
        try:
            res = requests.get(url, headers=HEADERS)
            if res.status_code != 200:
                raise requests.RequestException
        except requests.RequestException:
            print("Warning: request failed for url:", url, file=sys.stderr)
            time.sleep(1)
        else:
            break
    return res.content


# PARSERS #

def parse_offers_list(content):
    soup = BeautifulSoup(content, "lxml")
    links = [
        (l.get_text(), l.get("href"))
        for l in soup("a")
        if l.get("href") and re.match("/locations/[0-9]+.*", l.get("href"))
    ]
    return [
        (
            l[0].replace("\xa0", " "),
            l[1].replace("/locations/", "").replace(".htm/", "")
        )
        for l in links
    ]


def parse_text_from_offer(content):
    soup = BeautifulSoup(content, "lxml")
    text = soup.find("div", {"data-qa-id": "adview_description_container"})
    return text.get_text().replace("\n", " ")


def is_offer_interesting(offer_text):
    if re.match(".*(foncia|coloc|sous[- ]lo|ascenseur)", offer_text, re.I):
        return False
    return True


# WRAPPERS #

def check_offer(offer):
    offer_title, offer_id = offer[0], offer[1]
    offer_content = get_url_content(OFFER_URL.format(offer_id))
    offer_text = parse_text_from_offer(offer_content)
    offer_text = "    ".join([offer_title, offer_text])
    is_interesting = is_offer_interesting(offer_text)
    if is_interesting:
        print(offer_text, "\n")  # DEBUG
    return is_interesting


# MAIN #

if __name__ == "__main__":
    prev_results = read_flats_id()
    results = []
    with Pool(POOL_SIZE) as pool:
        for page in range(1, MAX_PAGES):
            print("Searching page", page)  # DEBUG
            search_content = get_url_content(SEARCH_URL.format(page))
            offers = parse_offers_list(search_content)  # titles, ids
            offers = [
                (offer_title, offer_id)
                for offer_title, offer_id in offers
                if offer_id not in prev_results
            ]
            if not len(offers):
                break
            are_intersting = pool.map(check_offer, offers)
            results += [
                offer[1] for i, offer in enumerate(offers) if are_intersting[i]
            ]
    handle_results(results)
