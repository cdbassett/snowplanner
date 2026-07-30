import itertools

from snowrunner_utils import *


for region_area in iterate_region_area():
    for typ in ("normal","mud","snow","icon"):
        print(slugify_region_area(region_area.region, region_area.abbrev)+"_"+typ)


