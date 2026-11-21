from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0005_add_region_area_truck_info')]

    initial = False

    operations = [
        ops.CreateModel(
            name='TaskGiver',
            fields=[
                ('id', fields.IntField(primary_key=True, unique=True, db_index=True)),
                ('area_id', fields.CharField(max_length=8)),
                ('x', fields.SmallIntField(null=True)),
                ('y', fields.SmallIntField(null=True)),
                ('objective', fields.ForeignKeyField('models.Objective', source_field='objective_id', db_constraint=True, to_field='id', related_name='task_givers', on_delete=OnDelete.CASCADE)),
                ('zone_id', fields.CharField(max_length=70)),
                ('primary', fields.BooleanField(default=True)),
            ],
            options={'table': 'task_giver', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
