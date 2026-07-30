from __future__ import print_function
# -*- coding: utf-8 -*-
import sys
import os
import os.path
import datetime
from datetime import timedelta
import codecs
import csv

import requests


def printList(title, lst, inset = "", file=sys.stdout):
    print("{}{}".format(inset, title), file=file)

    for item in lst:
        print(u"{}\t{}".format(inset, item), file=file)


def WriteUtf8File(filename, text):
    with codecs.open(filename, "wb", "utf-8") as f:
        f.write(text)

def ReadUtf8File(filename):
    with codecs.open(filename, "rb", "utf-8") as f:
        return f.read()


def read_tsv_file(fname):
    with open(fname, encoding="utf-8") as in_f:
        reader = csv.reader(in_f, delimiter="\t")
        yield from reader

class FileCache:
    """
    Usage:
    reader = FileCache('data.txt')
    print(reader.get_content()) # First read, populates cache
    print(reader.get_content()) # Second read, returns cache
    """
    def __init__(self, filepath, process=None):
        self.filepath = filepath
        self.cache = None
        self.last_mtime = 0
        self.process = process

    def get_content(self, indicate_cached=False):
        # 1. Get the current modification time of the file
        current_mtime = os.path.getmtime(self.filepath)
        cached = True

        # 2. Compare current mtime with stored mtime
        if current_mtime != self.last_mtime:
            cached = False
#            print("File changed. Re-reading from disk...")
            if self.process:
                self.cache = self.process(self.filepath)
            else:
                with open(self.filepath, 'r') as f:
                    self.cache = f.read()

            self.last_mtime = current_mtime
#        else:
#            print("Returning cached content...")

        return (self.cache, cached) if indicate_cached else self.cache

def updateRetrieveCachePage(filename, url, max_age = timedelta(days=1)):
    print("Using {}".format(filename))
    needUpdate = False

    if not os.path.isfile(filename):
        print("Couldn't find {}, will retrieve".format(filename))
        needUpdate = True
    else:
        file_mod_time = datetime.datetime.fromtimestamp(os.stat(filename).st_mtime)  # This is a datetime.datetime object!
        now = datetime.datetime.today()
#        max_age = timedelta(minutes=5)
#        print(now)
#        print(file_mod_time)
#        print(max_age)

        if now - file_mod_time > max_age:
            print("{} is old, will retrieve".format(filename))
            needUpdate = True


    if needUpdate:
        response = requests.get(url)
        pageContent = response.text
        WriteUtf8File(filename, pageContent)
    else:
        pageContent = ReadUtf8File(filename)

    return needUpdate

def get_cached_file(file_path, getter, params=(), only_if_older_than = None, writer=WriteUtf8File, reader=ReadUtf8File):
    needUpdate = False

    if not os.path.isfile(file_path):
        print(u"Couldn't find {}, will retrieve".format(file_path))
        needUpdate = True
    else:
        if only_if_older_than:
            file_mod_time = datetime.datetime.fromtimestamp(os.stat(file_path).st_mtime)  # This is a datetime.datetime object!

            if file_mod_time < only_if_older_than:
                print(u"{} is old, will retrieve".format(file_path))
                needUpdate = True

    contents = None

    if not needUpdate:
        contents = reader(file_path)
        needUpdate = not contents

    if needUpdate:
        contents = getter(*params)

        if contents != None:
            writer(file_path, contents)

    return contents, needUpdate


def WriteFile(filename, text):
    with codecs.open(filename, "wb", "utf-8") as f:
        f.write(text)

def ReadFile(filename):
    with codecs.open(filename, "rb", "utf-8") as f:
        return f.read()


def updateRetrieveCachePage(filename, url):
    print(filename)
    needUpdate = False

    if not os.path.exists(filename):
        print("Couldn't find {}, will retrieve".format(filename))
        needUpdate = True
    else:
        file_mod_time = datetime.datetime.fromtimestamp(os.stat(filename).st_mtime)  # This is a datetime.datetime object!
        now = datetime.datetime.today()
        max_delay = timedelta(days=1)
#        max_delay = timedelta(minutes=5)
#        print(now)
#        print(file_mod_time)
#        print(max_delay)

        if now - file_mod_time > max_delay:
            print("{} is old, will retrieve".format(filename))
            needUpdate = True


    if needUpdate:
        response = requests.get(url)
        pageContent = response.text
        WriteFile(filename, pageContent)
    else:
        pageContent = ReadFile(filename)

    return pageContent



