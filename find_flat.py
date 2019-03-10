#!/usr/bin/env python3

import sys
import time
import re
import os
from multiprocessing import Pool, Process

import requests
from bs4 import BeautifulSoup

DEBUG = bool(os.environ.get("DEBUG", False))

MAX_PAGES = 42  # TODO: scrap it

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:65.0) "
    + "Gecko/20100101 Firefox/65.0",
    "Accept": "text/html",
    "Accept-Language": "en-US",
    "Accept-Encoding": "identity"
}

# SEARCH_FILTERS #
SURFACE_MIN = "20"
PRICE_MIN = "600"
PRICE_MAX = "800"
FURNISHED = True


# FILTERS #
def is_offer_interesting(offer_text):
    if re.match(r".*(foncia|coloc|sous[- ]lo)", offer_text, re.I):
        return False
    if re.match(r".*(ascen[sc]eur)", offer_text, re.I) and not re.match(
            r".*(rdc|rez|(1\s?er?|premier)\s+[ée]tage)", offer_text, re.I
    ):
        return False
    if re.match(
            r".*(([2-9]\s?[eè](me)?"
            + r"|(deuxi|troisi|quatri|cinqi|sixi|septi|huiti|neu[vf]i)[eè]me)"
            + r"\s+[ée]tage)", offer_text, re.I
    ):
        return False
    return True


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


# IO #
def read_flats_id(results_file):
    if DEBUG:
        return []
    try:
        with open(results_file, mode="r") as f:
            flats_id = [line.rstrip("\n") for line in f]
    except FileNotFoundError:
        return []
    return flats_id


def scrap_wrapper(scrapper_class):
    scrapper_class().scrap()


# BASE SCRAPPER CLASS #
class BaseScrapper():
    def __init__(self):
        self.results_file = "flats_id-" + self.__class__.__name__ + ".list"

    def _handle_results(self, results):  # TODO: move outside
        if DEBUG:
            print(results, len(results))  # DEBUG
            return
        with open(self.results_file, mode="a") as f:
            print("\n".join(results), file=f)
        for offer_id in results:
            os.system("firefox " + self.offer_url.format(offer_id))

    def _check_offer(self, offer):
        offer_title, offer_id = offer[0], offer[1]
        offer_content = get_url_content(self.offer_url.format(offer_id))
        offer_text = self._parse_text_from_offer(offer_content)
        offer_text = "    ".join([offer_title, offer_text])
        is_interesting = is_offer_interesting(offer_text)
        if is_interesting:
            print(offer_text, "\n")  # DEBUG
        return is_interesting

    def scrap(self):
        prev_results = read_flats_id(self.results_file)
        results = []
        with Pool(self.offers_per_page) as pool:
            for page in range(1, MAX_PAGES):
                print("Searching page", page, self.__class__.__name__)  # DEBUG
                search_content = get_url_content(self.search_url.format(page))
                offers, is_last = self._parse_offers_list(search_content, page)
                offers = [
                    (offer_title, offer_id)
                    for offer_title, offer_id in offers
                    if offer_id not in prev_results
                ]
                are_intersting = pool.map(self._check_offer, offers)
                results += [
                    offer[1] for i, offer in enumerate(offers)
                    if are_intersting[i]
                ]
                if is_last:
                    break
        self._handle_results(results)


class Leboncoin(BaseScrapper):
    offers_per_page = 35  # pool_size
    results_file = "flats_id-lbc.list"
    search_url = "https://www.leboncoin.fr/recherche/?" \
        + "&".join([
            "category=10",  # region"
            "locations=Paris",
            "price=" + PRICE_MIN + "-" + PRICE_MAX,
            "square=" + SURFACE_MIN + "-max",
            "furnished=" + "1" if FURNISHED else "0",
            # "rooms=2",
            "real_estate_type=2",  # appart
            "page={}"
        ])
    offer_url = "https://www.leboncoin.fr/locations/{}.htm/"

    def _parse_offers_list(self, content, page):
        soup = BeautifulSoup(content, "lxml")
        is_last = not bool([
            l.get("href")
            for l in soup("a")
            if l.get("href") and "page=" + str(page + 1) in l.get("href")
        ])

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
        ], is_last

    def _parse_text_from_offer(self, content):
        soup = BeautifulSoup(content, "lxml")
        text = soup.find("div", {"data-qa-id": "adview_description_container"})
        # TODO: return None if no picture
        # TODO: return None if foncia anywhere in page
        return text.get_text().replace("\n", " ")


class Pap(BaseScrapper):
    offers_per_page = 10  # pool_size
    results_file = "flats_id-pap.list"
    search_url = "https://www.pap.fr/annonce/locations-" + \
        "-".join([
            "appartement" + "-meuble" if FURNISHED else "",
            "paris-75-g439",
            "entre-" + PRICE_MIN + "-et-" + PRICE_MAX + "-euros",
            "a-partir-de-" + SURFACE_MIN + "-m2",
            "{}"
        ])
    offer_url = "https://www.pap.fr/annonces/appartement-{}"

    def _parse_offers_list(self, content, unused):
        soup = BeautifulSoup(content, "lxml")
        is_last = not bool(soup.find("li", {"class": "next"}))
        links = [
            (l.get_text(), l.get("href"))
            for l in soup("a")
            if l.get("href")
            and re.match("/annonces/appartement-.*", l.get("href"))
        ]
        return [
            (
                l[0].replace("\xa0", " ").replace("\n", " "),
                l[1].replace("/annonces/appartement-", "")
            )
            for l in links
        ], is_last

    def _parse_text_from_offer(self, content):
        soup = BeautifulSoup(content, "lxml")
        text = soup.find("div", {"class": "item-description"})
        # TODO: return None if no picture
        # TODO: return None if foncia anywhere in page
        return text.get_text().replace("\n", " ").replace("\t", " ")\
                              .replace("\r", "").replace("\xa0", " ")


class Immojeune(BaseScrapper):
    offers_per_page = 8  # pool_size
    search_url = "https://www.immojeune.com/location-etudiant/" \
        + "paris-75.html?" + "&".join([
            "priceMin=" + PRICE_MIN,
            "priceMax=" + PRICE_MAX,
            "surfaceMin=" + SURFACE_MIN,
            "surfaceMax=100",
            "furnished=" + "1" if FURNISHED else "0",
            "around=0",
            "page={}"
        ])
    offer_url = "https://www.immojeune.com/location-etudiant/{}.html"

    def _parse_offers_list(self, content, unused):
        soup = BeautifulSoup(content, "lxml")
        is_last = not bool([
            l for l in soup("a") if l.get_text() == 'Suivant'
        ])
        links = [
            (l.get_text(), l.get("href"))
            for l in soup("a")
            if l.get("href")
            and l.get_text() != "\n\n"
            and "\nDéposer ma candidature\n" not in l.get_text()
            and "chambre" not in l.get("href")
            and re.match("/location-etudiant/.*/.*", l.get("href"))
        ]
        return [
            (
                l[0].replace("\n", ""),
                l[1].replace("/location-etudiant/", "").replace(".html", "")
            )
            for l in links
        ], is_last

    def _parse_text_from_offer(self, content):
        soup = BeautifulSoup(content, "lxml")
        text = soup.find("div", {"class": "content"}).get_text()
        text += "".join([
            t.get_text()
            for t in soup.find("table", {"class": "informations"})(
                    "td", {"class": "col-align-center"}
            )
        ])
        # TODO: return None if no picture
        # TODO: return None if foncia anywhere in page
        return text.replace("\n", " ")


# MAIN #
if __name__ == "__main__":
    scrappers = [Leboncoin, Pap, Immojeune]
    processes = []
    while len(scrappers) > 1:
        p = Process(
            target=scrap_wrapper,
            args=(scrappers[0],),
            daemon=False
        )
        p.start()
        processes.append(p)
        scrappers.pop(0)
    scrap_wrapper(scrappers[0])
    for p in processes:
        p.join()
        p.close()
