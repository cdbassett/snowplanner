from utils.snowrunner_utils import *
from combine_images import combine_images_no_resize

src_map_image_dir = Path("~/projects/old_snowmapper/map_images_org/").expanduser()
combine_to__dir = Path("~/Downloads/").expanduser()
ic(src_map_image_dir)

# PYTHONPATH=~/projects p3 -m dev.combine_region_map_images

def get_image_name_ex(area_info, typ="normal", base=""):
    return f"{base}{slugify_region_area(area_info.region, area_info.abbrev)}_{typ}.png"

def src_image_path(f):
    return str(src_map_image_dir/ f)

for region, region_areas in itertools.groupby(iterate_region_area(), itemgetter(1)):
    region_areas = list(region_areas)
    print(region)

    if len(region_areas) > 1:
        filenames = list(map(get_image_name_ex, region_areas))
        image_paths = list(map(src_image_path, filenames))
        print(image_paths)
        combine_images_no_resize(image_paths, combine_to__dir / f"combined {region}.png", "white")




