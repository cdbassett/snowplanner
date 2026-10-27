from utils.snowrunner_utils import *
from split_combined_images import split_combined_image

src_map_image_dir = Path("~/projects/old_snowplanner/map_images_org/").expanduser()
dst_map_image_dir = Path("~/projects/snowplanner/new_map_images/").expanduser()
dst_map_image_dir.mkdir(parents=True, exist_ok=True)
combine_to__dir = Path("~/Downloads/").expanduser()
split_from_dir = Path("~/Downloads/").expanduser()
ic(src_map_image_dir)

# PYTHONPATH=~/projects p3 -m dev.split_combined_region_map_images


def get_image_name_ex(area_info, typ="normal", base=""):
    return f"{base}{slugify_region_area(area_info.region, area_info.abbrev)}_{typ}.png"

def src_image_path(f):
    return str(src_map_image_dir/ f)

def dst_image_path(f):
    return str(dst_map_image_dir/ f)

for region, region_areas in itertools.groupby(iterate_region_area(), itemgetter(1)):
    region_areas = list(region_areas)
    print(region)

    if len(region_areas) > 1:
        filenames = list(map(get_image_name_ex, region_areas))
        image_paths = list(map(src_image_path, filenames))
        print(image_paths)
        split_combined_image(image_paths, split_from_dir / f"{region.lower().replace(' ', '_')}_transformed.jpeg", dst_map_image_dir)




