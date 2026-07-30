#!/usr/bin/env python3
import os

from bs4 import BeautifulSoup
from icecream import ic

from utilities import updateRetrieveCachePage
from snowrunner_utils import *


url = 'https://www.maprunner.info/cargo'


def parsePage(pageContent):
    soup = BeautifulSoup(pageContent, features="lxml")
    table = soup.find('table')
    rows = [ [td.a and td.a.get("href") or td.getText(separator=" ") for td in tr.findAll('td')] for tr in table.findAll('tr') ]
    return sorted((row for row in rows if "".join(row)), key = lambda x: x[3] or x[0])


def updateRetrieveAndParseCachePage(filename, url):
    pageContent = updateRetrieveCachePage(filename, url)
    return parsePage(pageContent)

rows = updateRetrieveAndParseCachePage(make_snowrunner_data_path("snowrunner_cargo.html"), url)

def conv_name(s):
    return " ".join(map(str.capitalize, s.replace("-", " ").split()))

def main():
    results = []

    for row in rows:
        row = (row + [""] * 5)[:4]

        try:
            region, area, *_ = row[3].split("?")[0].split("/")[1:]
        except:
            print(row)
            raise
        results.append(([conv_name(region), conv_name(area), row[0], "|".join(sorted(parse_cargo(row[2]))), row[3]]))

    write_snowrunner_data_tsv_file("snowrunner_cargo_reformatted.tsv", sorted(results, key=itemgetter(0,1,2)))


if __name__ == "__main__":
    main()
