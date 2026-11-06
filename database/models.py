from tortoise import fields
from tortoise.models import Model


def string_id(**kw):
    return fields.CharField(max_length=70, **kw)

def area_id_field(**kw):
    return fields.CharField(8, **kw)

class AreaMixin():
    area_id = area_id_field()

class PositionMixin(AreaMixin):
    x = fields.SmallIntField(null=True)
    y = fields.SmallIntField(null=True)


class MapItem(Model, PositionMixin):
    id = string_id(pk=True)
    name = fields.CharField(max_length=255)
    item_type = fields.CharField(max_length=10) # (truck, trailer, source, craft, gate, location)
    cargo_items = fields.ReverseRelation["SourceCargoItem"]
    obj_item_deliveries = fields.ReverseRelation["ObjectiveItem"]
    obj_locker = fields.ForeignKeyField("models.Objective", null=True, related_name="map_items_locked_by") # if a e.g. source isn't available until an objective is completed
    to_area_id = area_id_field(null=True) # gates use this
    to_map_item_id = string_id(null=True) # gates use this, not doign full relation bc 1) order of insertion is not guranteed and fails db cponstraint, 2) every one being present (weird extra thigns to parse etc.) not guaranteed
    completed = fields.BooleanField(default=False, null=True) # for standalone map items like trucks

    class Meta:
        table = "map_item"

    def __str__(self):
        return self.name

class Objective(Model, AreaMixin):
    id = string_id(pk=True)
    name = fields.CharField(max_length=255)
    completed = fields.BooleanField(default=False)
    obj_items = fields.ReverseRelation["ObjectiveItem"]
    obj_prereqs = fields.ReverseRelation["ObjectivePrereq"]
    obj_prereq_of = fields.ReverseRelation["ObjectivePrereq"]
    obj_type = fields.CharField(null=True, max_length=10) # (task, contract, contest) although I don't care about contests so I don't populate with them
    reward_money = fields.SmallIntField(null=True)
    reward_exp = fields.SmallIntField(null=True)
    reward_item = fields.CharField(null=True, max_length=50)

    class Meta:
        table = "objective"

    def __str__(self):
        return self.name

class ObjectivePrereq(Model):
    id = fields.IntField(pk=True)
    objective = fields.ForeignKeyField(Objective, related_name='obj_prereqs')
    prereq_obj = fields.ForeignKeyField(Objective, related_name="obj_prereq_of")
    #prereq_obj = fields.OneToOneField(Objective, related_name="obj_prereq_of")

    class Meta:
        table = "obj_prereq"

    def __str__(self):
        # return self.prereq_obj_id
        return self.id

# if there is a source, it is indicated by the map_item
class ObjectiveItem(Model):
    id = string_id(pk=True)
    map_item = fields.ForeignKeyField(MapItem, null=True, related_name='obj_items') # confirmed that a few objectives have multiple obj items pointing to same map_item, e.g. delivering same trailer to multiple locations
    item_type = fields.CharField(max_length=10) # (truck, cargo, visit)
    objective = fields.ForeignKeyField(Objective, related_name='obj_items')
    name = fields.CharField(max_length=50)
    deliver_loc = fields.ForeignKeyField(MapItem, related_name="obj_item_deliveries")
    count = fields.SmallIntField(null=True)
    completed = fields.BooleanField(default=False)
    stage = fields.SmallIntField(null=True)

    class Meta:
        table = "obj_item"

    def __str__(self):
        return self.name

def current_cargo_count(src_cargo_item):
    if src_cargo_item.initial_cnt is not None:
        if src_cargo_item.current_cnt is not None:
            return min(src_cargo_item.initial_cnt, max(0, src_cargo_item.current_cnt))
        else:
            return src_cargo_item.initial_cnt

class SourceCargoItem(Model):
    id = string_id(pk=True)
    map_item = fields.ForeignKeyField(MapItem, related_name='cargo_items')
    name = string_id()
    initial_cnt = fields.SmallIntField(null=True)
    current_cnt = fields.SmallIntField(null=True)
    craft_desc = fields.CharField(max_length=255, null=True) # recipe if a crafting location

    class Meta:
        table = "src_cargo_item"

    def __str__(self):
        return self.name



# --- Delivery plans: user-specific data, deliberately NOT in database/config.py TABLE_ORDER (never dumped to or seeded from fixtures).
# Map items / objective items are referenced by plain string ids, not FKs, so reseeding the reference tables can't cascade into plans.

class DeliveryPlan(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100)
    region = fields.CharField(max_length=100) # region name as used by the app; a plan lives in exactly one region
    completed = fields.BooleanField(default=False)
    visible = fields.BooleanField(default=False) # the one plan per region drawn on the map
    created = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "delivery_plan"

    def __str__(self):
        return self.name


class PlanStop(Model):
    id = fields.IntField(pk=True)
    plan = fields.ForeignKeyField("models.DeliveryPlan", related_name="stops", on_delete=fields.CASCADE)
    position = fields.IntField() # order within the plan
    area_id = area_id_field()
    x = fields.SmallIntField() # real map position, 0-1000 (not the overlap-corrected drawn position)
    y = fields.SmallIntField()
    map_item_id = fields.CharField(max_length=70, null=True) # set when the stop snapped to an existing location
    label = fields.CharField(max_length=255, default="")
    completed = fields.BooleanField(default=False)

    class Meta:
        table = "plan_stop"
        ordering = ["position"]


class PlanCargo(Model):
    id = fields.IntField(pk=True)
    stop = fields.ForeignKeyField("models.PlanStop", related_name="cargo", on_delete=fields.CASCADE)
    action = fields.CharField(max_length=7) # "pickup" or "dropoff"
    kind = fields.CharField(max_length=7, default="cargo") # "cargo", "truck" or "trailer"
    name = fields.CharField(max_length=255)
    count = fields.SmallIntField(default=1)
    ref_id = fields.CharField(max_length=70, null=True) # vehicle MapItem id or ObjectiveItem id it came from

    class Meta:
        table = "plan_cargo"
        ordering = ["id"]
