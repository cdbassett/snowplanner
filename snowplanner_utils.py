from pathlib import Path
from utils.snowrunner_utils import *
#from database import *


snowplanner_base_dir = Path(__file__).resolve().parent
snowplanner_map_image_dir =  os.path.join(snowplanner_base_dir, r"map_images")
snowplanner_data_dir =  os.path.join(snowplanner_base_dir, r"data")

obj_item_loc_key = lambda r: r.deliver_loc.name
obj_item_stage_loc_key = lambda r: (r.stage or 0, r.deliver_loc.name)
obj_item_stage_key = lambda r: r.stage or 0

# assumes all obj_items are for same objective
def determine_stage_blocking(obj_items, obj_prereqs):
    multi_stages = obj_items[0].stage is not None and max(map(obj_item_stage_key, obj_items)) > 0
    blocked_stages = set()
    blocked = any(not prereq.prereq_obj.completed for prereq in obj_prereqs)

    # trigger = objective.name == "Getting Rusty (C)"

    if multi_stages and not blocked:
        last_stage = 0
        block_rest = False
        obj_items = sorted(obj_items, key=obj_item_stage_key)

        for stage, stage_obj_items in itertools.groupby(obj_items, obj_item_stage_key):
            stage = stage or 0

            if block_rest and stage != last_stage:
                blocked_stages.add(stage)

            if any(not obj_item.completed for obj_item in stage_obj_items):
                block_rest = True

            # if trigger:
            #     ic(stage, stage_obj_items, next_stage_blocked)

            last_stage = stage

    return multi_stages, blocked_stages

