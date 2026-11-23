from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0010_add_repair_after_stage')]

    initial = False

    operations = [
        ops.CreateModel(
            name='ObjectiveVisit',
            fields=[
                ('id', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=70)),
                ('area_id', fields.CharField(max_length=8)),
                ('x', fields.SmallIntField(null=True)),
                ('y', fields.SmallIntField(null=True)),
                ('objective', fields.ForeignKeyField('models.Objective', source_field='objective_id', db_constraint=True, to_field='id', related_name='visits', on_delete=OnDelete.CASCADE)),
                ('stage', fields.SmallIntField()),
                ('zone_id', fields.CharField(max_length=70)),
                ('name', fields.CharField(max_length=200)),
                ('completed', fields.BooleanField(default=False)),
            ],
            options={'table': 'objective_visit', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
