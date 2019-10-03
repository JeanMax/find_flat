#!/usr/bin/env python3

import sys
import time
import re
import os
import inspect
from multiprocessing import Pool, Process

import requests
from bs4 import BeautifulSoup

DEBUG = bool(os.environ.get("DEBUG", False))
HERE = os.path.dirname(os.path.realpath(inspect.getsourcefile(lambda: 0)))
LOG_DIR = os.path.join(HERE, "logs")
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
FURNISHED = False


# FILTERS #
def is_offer_interesting(offer_text):
    # TODO: (before)
    #     return None if no picture
    #     return None if foncia anywhere in page
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


def write_flats_id(results, results_file):
    if results:
        with open(results_file, mode="a") as f:
            print("\n".join(results), file=f)


# STUPID WRAPPER #
def scrap_wrapper(scrapper_class):
    scrapper_class().scrap()


class BaseScrapper():
    max_pages = 42

    def __init__(self):
        filename = os.path.join(LOG_DIR, "flats_id-" + self.__class__.__name__)
        self.good_results_file = filename + ".good"
        self.bad_results_file = filename + ".bad"

    def _handle_results(self, good_results, bad_results):
        if DEBUG:
            print(good_results, len(bad_results))  # DEBUG
            return
        write_flats_id(good_results, self.good_results_file)
        write_flats_id(bad_results, self.bad_results_file)
        for offer_id in good_results:
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
        prev_results = read_flats_id(self.good_results_file)
        prev_results += read_flats_id(self.bad_results_file)
        good_results = []
        bad_results = []
        with Pool(self.offers_per_page) as pool:
            for page in range(1, self.max_pages):
                print("Searching page", page, self.__class__.__name__)  # DEBUG
                search_content = get_url_content(self.search_url.format(page))
                offers, is_last = self._parse_offers_list(search_content, page)
                offers = [
                    (offer_title, offer_id)
                    for offer_title, offer_id in offers
                    if offer_id not in prev_results
                ]
                are_intersting = pool.map(self._check_offer, offers)
                good_results += [
                    offer[1] for i, offer in enumerate(offers)
                    if are_intersting[i]
                ]
                bad_results += [
                    offer[1] for i, offer in enumerate(offers)
                    if not are_intersting[i]
                ]
                if is_last:
                    break
        self._handle_results(good_results, bad_results)


class Leboncoin(BaseScrapper):
    offers_per_page = 35  # pool_size
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
        return text.get_text().replace("\n", " ")


class Pap(BaseScrapper):
    offers_per_page = 10  # pool_size
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
        # text += "".join([
        #     t.get_text()
        #     for t in soup.find("table", {"class": "informations"})(
        #             "td", {"class": "col-align-center"}
        #     )
        # ])
        return text.replace("\n", " ")


class Seloger(BaseScrapper):
    offers_per_page = 20  # pool_size
    search_url = "https://www.seloger.com/list.htm?" \
        + "&".join([
            "types=1",
            "projects=1",
            "enterprise=0",
            "furnished=" + "1" if FURNISHED else "0",
            "price=" + PRICE_MIN + "/" + PRICE_MAX,
            "surface=" + SURFACE_MIN + "/NaN",
            "places=[{{ci:750056}}]",
            "qsVersion=1.0",
            "LISTING-LISTpg={}"
        ])
    offer_url = "https://www.seloger.com/annonces/locations/appartement/{}.htm"

    def _parse_offers_list(self, content, unused):
        soup = BeautifulSoup(content, "lxml")
        is_last = not bool(soup.find("a", {"class": "pagination-next"}))
        links = [
            (l.get_text(), l.get("href"))
            for l in soup("a")
            if l.get("href")
            and "\n\n" not in l.get_text()
            and re.match("https://www.seloger.com/annonces/.*", l.get("href"))
        ]
        return [
            (
                l[0],
                l[1].split("?")[0].replace(
                    "https://www.seloger.com/annonces/locations/appartement/",
                    ""
                ).replace(".htm", "")
            )
            for l in links
        ], is_last

    def _parse_text_from_offer(self, content):
        soup = BeautifulSoup(content, "lxml")
        text = soup.find("input", {"name": "description"}).get("value")
        return text.replace("\n", " ").replace("\r", "")


class Paruvendu(BaseScrapper):
    offers_per_page = 10  # pool_size
    search_url = "https://www.paruvendu.fr/immobilier/location/appartement/" \
        + ("meuble" if FURNISHED else "") \
        + "/paris-75/?" \
        + "&".join([
            "nbp=0",
            "tt=5",
            "tbApp=1",
            "at=1",
            "nbp0=99",
            "sur0=" + SURFACE_MIN,
            "px0=" + PRICE_MIN,
            "px1=" + PRICE_MAX,
            "lo=75",
            "ddlFiltres=nofilter",
            "p={}"
        ])
    offer_url = "https://www.paruvendu.fr/immobilier/location/{}"

    def _parse_offers_list(self, content, unused):
        soup = BeautifulSoup(content, "lxml")
        is_last = not bool([
            a for a in soup("a", {"class": "page"})
            if "suivante" in a.get_text()
        ])
        links = [
            (l.get_text(), l.get("href"))
            for l in soup("a")
            if l.get("href")
            and re.match("/immobilier/location/.*/.*/.*", l.get("href"))
            and l.get_text() == "Voir l'annonce"
        ]
        return [
            (
                l[0],
                l[1].replace("/immobilier/location/", "")
            )
            for l in links
        ], is_last

    def _parse_text_from_offer(self, content):
        soup = BeautifulSoup(content, "lxml")
        text = soup.find("div", {"class": "im12_txt_ann im12_txt_ann_auto"})
        return text.get_text().replace("\n", " ").replace("\r", "")


# MAIN #
if __name__ == "__main__":
    scrappers = [
        Leboncoin,
        Pap,
        Immojeune,
        # Seloger,
        Paruvendu,
    ]
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
