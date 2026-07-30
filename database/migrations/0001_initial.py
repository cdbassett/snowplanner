from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.CreateModel(
            name='Objective',
            fields=[
                ('area_id', fields.CharField(max_length=8)),
                ('id', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=70)),
                ('name', fields.CharField(max_length=255)),
                ('completed', fields.BooleanField(default=False)),
                ('obj_type', fields.CharField(null=True, max_length=10)),
                ('reward_money', fields.SmallIntField(null=True)),
                ('reward_exp', fields.SmallIntField(null=True)),
                ('reward_item', fields.CharField(null=True, max_length=50)),
            ],
            options={'table': 'objective', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model', 'AreaMixin'],
        ),
        ops.CreateModel(
            name='MapItem',
            fields=[
                ('area_id', fields.CharField(max_length=8)),
                ('x', fields.SmallIntField(null=True)),
                ('y', fields.SmallIntField(null=True)),
                ('id', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=70)),
                ('name', fields.CharField(max_length=255)),
                ('item_type', fields.CharField(max_length=10)),
                ('obj_locker', fields.ForeignKeyField('models.Objective', source_field='obj_locker_id', null=True, db_constraint=True, to_field='id', related_name='map_items_locked_by', on_delete=OnDelete.CASCADE)),
                ('to_area_id', fields.CharField(null=True, max_length=8)),
                ('to_map_item_id', fields.CharField(null=True, max_length=70)),
                ('completed', fields.BooleanField(null=True, default=False)),
            ],
            options={'table': 'map_item', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model', 'PositionMixin'],
        ),
        ops.CreateModel(
            name='ObjectiveItem',
            fields=[
                ('id', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=70)),
                ('map_item', fields.ForeignKeyField('models.MapItem', source_field='map_item_id', null=True, db_constraint=True, to_field='id', related_name='obj_items', on_delete=OnDelete.CASCADE)),
                ('item_type', fields.CharField(max_length=10)),
                ('objective', fields.ForeignKeyField('models.Objective', source_field='objective_id', db_constraint=True, to_field='id', related_name='obj_items', on_delete=OnDelete.CASCADE)),
                ('name', fields.CharField(max_length=50)),
                ('deliver_loc', fields.ForeignKeyField('models.MapItem', source_field='deliver_loc_id', db_constraint=True, to_field='id', related_name='obj_item_deliveries', on_delete=OnDelete.CASCADE)),
                ('count', fields.SmallIntField(null=True)),
                ('completed', fields.BooleanField(default=False)),
                ('stage', fields.SmallIntField(null=True)),
            ],
            options={'table': 'obj_item', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='ObjectivePrereq',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('objective', fields.ForeignKeyField('models.Objective', source_field='objective_id', db_constraint=True, to_field='id', related_name='obj_prereqs', on_delete=OnDelete.CASCADE)),
                ('prereq_obj', fields.ForeignKeyField('models.Objective', source_field='prereq_obj_id', db_constraint=True, to_field='id', related_name='obj_prereq_of', on_delete=OnDelete.CASCADE)),
            ],
            options={'table': 'obj_prereq', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='SourceCargoItem',
            fields=[
                ('id', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=70)),
                ('map_item', fields.ForeignKeyField('models.MapItem', source_field='map_item_id', db_constraint=True, to_field='id', related_name='cargo_items', on_delete=OnDelete.CASCADE)),
                ('name', fields.CharField(max_length=70)),
                ('initial_cnt', fields.SmallIntField(null=True)),
                ('current_cnt', fields.SmallIntField(null=True)),
                ('craft_desc', fields.CharField(null=True, max_length=255)),
            ],
            options={'table': 'src_cargo_item', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
