from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0006_add_task_giver')]

    initial = False

    operations = [
        ops.CreateModel(
            name='ObjectiveRepair',
            fields=[
                ('id', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=70)),
                ('objective', fields.ForeignKeyField('models.Objective', source_field='objective_id', db_constraint=True, to_field='id', related_name='repairs', on_delete=OnDelete.CASCADE)),
                ('map_item', fields.ForeignKeyField('models.MapItem', source_field='map_item_id', db_constraint=True, to_field='id', related_name='repairs', on_delete=OnDelete.CASCADE)),
                ('stage', fields.SmallIntField()),
                ('phase', fields.CharField(max_length=6)),
                ('completed', fields.BooleanField(default=False)),
            ],
            options={'table': 'objective_repair', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
