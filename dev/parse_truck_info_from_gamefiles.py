#!/usr/bin/env python3
from pathlib import Path

from snowrunner_utils import *

ipd = Path(snowrunner_initial_pak_dir)
media_path = ipd / "[media]"


truck_patterns = [
     "classes/trucks",
     "_dlc/**/classes/trucks",
     "classes/trucks/trailers",
     "_dlc/**/classes/trucks/trailers",
    ]

ns_map = {
    'region': 'http://codespeak.net/ns/test1', # 't' is an arbitrary prefix
    'b': 'http://codespeak.net/ns/test2'
}

def parse_snowrunner_truck(xml_file, is_trailer):
    root = parse_xml(encapsulate(xml_file.read_text(encoding='utf-8').replace("region:default", "region_default")))
    ui_desc = root.find(".//GameData//UiDesc")

    if not (name := ui_desc.attrib.get('UiName')):
#        print(xml_file.stem, ui_desc)

#        ui_desc = root.find(".//GameData//UiDesc/region:default", namespaces=ns_map)
        ui_desc = root.find(".//GameData//UiDesc/region_default")
#        ui_desc = root.find(".//GameData//UiDesc/*[local-name()=default]")
        name = ui_desc.attrib.get('UiName')

    if name:
        yield ["trailer" if is_trailer else "truck", xml_file.stem, name]
    else:
        print("Couldn't find UiName for {xml_file.stem}")


def main():
    records = []

    for truck_pattern in truck_patterns:
#        ic(media_path, truck_pattern)
        for xml_path in media_path.glob(truck_pattern + "/*.xml"):
            print(xml_path)
            records.extend(parse_snowrunner_truck(xml_path, "trailers" in str(xml_path)))

    if records:
        write_snowrunner_data_tsv_file("snowrunner_truck_trailer_info.generated.tsv", records)


if __name__ == "__main__":
    main()



